from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from validation.tools.replay_call_plan import build_replay_call_plan
from validation.tools.replay_call_plan_fixture import _fixture_binding


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
INTEGER_ENCODINGS = {"u32", "u64", "i32", "usize", "u16", "bool"}
INTEGER_C_TYPES = {
    "u32": {"uint32_t", "unsigned int"},
    "u64": {"uint64_t"},
    "i32": {"int32_t", "int"},
    "usize": {"size_t"},
    "u16": {"uint16_t", "unsigned short"},
    "bool": {"bool", "_Bool"},
}
BYTE_POINTER_TYPES = {
    "const unsigned char *",
    "const uint8_t *",
    "const void *",
}
STRING_POINTER_TYPES = {"const char *"}
MAX_CASES = 128
MAX_CASE_ID_BYTES = 128
MAX_STRING_BYTES = 64 * 1024
MAX_BUFFER_BYTES = 1024 * 1024
MAX_RENDERED_BYTES = 2 * 1024 * 1024


def render_c_oracle_call_plan(spec: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    plan = build_replay_call_plan(spec, repo_root)
    if plan.get("status") != "bound":
        return {
            "status": str(plan.get("status") or "unavailable"),
            "reason": str(plan.get("reason") or "bound ReplayCallPlan is unavailable"),
        }
    try:
        return _render_bound_plan(spec, plan, repo_root.resolve())
    except ValueError as exc:
        return {
            "status": "unavailable",
            "reason": str(exc),
            "replay_call_plan_sha256": plan.get("plan_sha256"),
        }


def validate_c_oracle_call_plan_harness(
    spec: dict[str, Any],
    contract: Any,
    harness_text: str,
    repo_root: Path,
) -> None:
    if not isinstance(contract, dict):
        raise ValueError("C oracle call-plan contract is missing")
    rendered = render_c_oracle_call_plan(spec, repo_root)
    if contract.get("status") == "not_used":
        if rendered.get("status") == "generated":
            raise ValueError("generated C oracle call-plan contract is missing")
        return
    if contract.get("status") != "generated":
        raise ValueError("C oracle call-plan contract status is invalid")
    if rendered.get("status") != "generated":
        raise ValueError("C oracle call-plan contract cannot be regenerated")
    expected_contract = {
        "status": "generated",
        "replay_call_plan_sha256": rendered["replay_call_plan_sha256"],
        "case_count": rendered["case_count"],
        "compared_fields": rendered["compared_fields"],
    }
    if contract != expected_contract:
        raise ValueError("C oracle call-plan contract drifted")
    marker = f"COracleCallPlan-SHA256: {rendered['replay_call_plan_sha256']}"
    if harness_text.count(marker) != 1:
        raise ValueError("C oracle call-plan marker is missing or duplicated")
    declarations = str(rendered["declarations"]).strip()
    statements = str(rendered["statements"])
    if declarations not in harness_text:
        raise ValueError("C oracle call-plan declarations drifted")
    if harness_text.count(statements) != 1:
        raise ValueError("C oracle call-plan target invocation or assertions drifted")


def _render_bound_plan(
    spec: dict[str, Any], plan: dict[str, Any], repo_root: Path
) -> dict[str, Any]:
    if plan.get("schema_version") != 1:
        raise ValueError("C oracle renderer currently requires ReplayCallPlan schema v1")
    if plan.get("omitted_c_parameters"):
        raise ValueError("C oracle renderer requires every C parameter to be mapped")
    if plan.get("fixture_assertions"):
        raise ValueError("C oracle renderer cannot treat fixture metadata as target output")
    assertions = plan.get("assertions")
    if (
        not isinstance(assertions, list)
        or len(assertions) != 1
        or assertions[0].get("actual") != "return"
    ):
        raise ValueError("C oracle renderer currently requires one direct return assertion")

    function_name = _identifier(plan.get("source_function_name"), "source function")
    signature = _matching_signature(spec, function_name)
    c_parameters = signature["parameters"]
    plan_parameters = plan.get("parameters")
    if not isinstance(plan_parameters, list):
        raise ValueError("ReplayCallPlan parameters are missing")
    by_c_parameter = {
        item.get("c_parameter"): item
        for item in plan_parameters
        if isinstance(item, dict)
    }
    c_names = [item["name"] for item in c_parameters]
    if (
        len(plan_parameters) != len(c_parameters)
        or len(by_c_parameter) != len(plan_parameters)
        or set(by_c_parameter) != set(c_names)
    ):
        raise ValueError("ReplayCallPlan C parameter mapping is not closed")

    assertion = assertions[0]
    return_type = _normalize_c_type(signature.get("return_type"))
    _require_scalar_type(return_type, str(assertion.get("encoding") or ""))
    pointer_width = _target_pointer_width(spec)
    fixture = _fixture_binding(spec, repo_root)
    cases = fixture["cases"]
    if len(cases) > MAX_CASES:
        raise ValueError("C oracle call plan has too many fixture cases")
    declarations: list[str] = [
        f"/* COracleCallPlan-SHA256: {plan['plan_sha256']} */\n"
    ]
    statements: list[str] = []
    for index, case in enumerate(cases):
        case_id = str(case.get("id") or f"case-{index}")
        _require_printable_ascii(case_id, "fixture case id", MAX_CASE_ID_BYTES)
        case_ident = _safe_ident(case_id)
        inputs = case.get("inputs")
        expected = case.get("expected")
        if not isinstance(inputs, dict) or not isinstance(expected, dict):
            raise ValueError(f"fixture case {case_id} is incomplete")
        arguments: list[str] = []
        for parameter in c_parameters:
            expression, declaration = _render_argument(
                parameter,
                by_c_parameter[parameter["name"]],
                inputs,
                f"case_{case_ident}_{index}_{parameter['name']}",
                pointer_width,
            )
            arguments.append(expression)
            if declaration:
                declarations.append(declaration)
        field = str(assertion.get("fixture_field") or "")
        _require_printable_ascii(field, "assertion fixture field", MAX_CASE_ID_BYTES)
        if field not in expected:
            raise ValueError(f"fixture case {case_id} is missing expected field {field}")
        expected_literal = _scalar_literal(
            return_type,
            str(assertion.get("encoding") or ""),
            expected[field],
            pointer_width,
        )
        actual = f"actual_{case_ident}_{index}"
        statements.extend(
            [
                f"  {return_type} {actual} = {function_name}({', '.join(arguments)});\n",
                f"  if ({actual} != {expected_literal}) {{\n",
                "    fprintf(stderr, "
                + _c_string_literal(f"{case_id} {field} mismatch\\n")
                + ");\n",
                "    return 1;\n",
                "  }\n",
                "  puts("
                + _c_string_literal(f"fixture case {case_id} {field} matched")
                + ");\n",
            ]
        )
    declaration_text = "".join(declarations) + "\n"
    statement_text = "".join(statements)
    if len((declaration_text + statement_text).encode("utf-8")) > MAX_RENDERED_BYTES:
        raise ValueError("C oracle call-plan source exceeds the rendering limit")
    return {
        "status": "generated",
        "declarations": declaration_text,
        "statements": statement_text,
        "definitions_after_target": "",
        "replay_call_plan_sha256": plan["plan_sha256"],
        "case_count": len(cases),
        "compared_fields": [assertion["fixture_field"]],
    }


def _matching_signature(spec: dict[str, Any], function_name: str) -> dict[str, Any]:
    matches = [
        item
        for item in spec.get("c_boundary", {}).get("signatures") or []
        if isinstance(item, dict) and item.get("function") == function_name
    ]
    if len(matches) != 1:
        raise ValueError("C oracle renderer requires exactly one matching C signature")
    raw_parameters = matches[0].get("parameters")
    if not isinstance(raw_parameters, list):
        raise ValueError("C signature parameters are missing")
    parameters = []
    for raw in raw_parameters:
        if not isinstance(raw, dict):
            raise ValueError("C signature parameter is invalid")
        parameters.append(
            {
                **raw,
                "name": _identifier(raw.get("name"), "C parameter"),
                "c_type": _normalize_c_type(raw.get("c_type")),
            }
        )
    return {**matches[0], "parameters": parameters}


def _render_argument(
    c_parameter: dict[str, Any],
    plan_parameter: dict[str, Any],
    inputs: dict[str, Any],
    variable: str,
    pointer_width: int,
) -> tuple[str, str]:
    source = plan_parameter.get("source")
    if not isinstance(source, dict):
        raise ValueError("ReplayCallPlan argument source is missing")
    source_kind = source.get("kind")
    if source_kind not in {"fixture_field", "encoded_length"}:
        raise ValueError("ReplayCallPlan argument source kind is unsupported")
    field = str(source.get("field") or "")
    if field not in inputs:
        raise ValueError(f"fixture input field {field} is missing")
    value = inputs[field]
    if value is None and "null_default" in source:
        value = source["null_default"]
    c_type = str(c_parameter["c_type"])
    if source_kind == "encoded_length":
        if source.get("encoding") != "hex":
            raise ValueError("encoded-length fixture source requires hex encoding")
        data = _decode_hex(value)
        _require_scalar_type(c_type, "usize")
        return _scalar_literal(c_type, "usize", len(data), pointer_width), ""
    encoding = str(source.get("encoding") or "")
    if encoding in INTEGER_ENCODINGS:
        _require_scalar_type(c_type, encoding)
        return _scalar_literal(c_type, encoding, value, pointer_width), ""
    if encoding == "string":
        if c_type not in STRING_POINTER_TYPES or not isinstance(value, str):
            raise ValueError("string fixture source requires const char *")
        _require_printable_ascii(value, "string fixture field", MAX_STRING_BYTES)
        return variable, f"static const char {variable}[] = {_c_string_literal(value)};\n"
    if encoding in {"hex_bytes", "u8_array"}:
        if c_type not in BYTE_POINTER_TYPES:
            raise ValueError("byte fixture source requires a supported const byte pointer")
        data = _decode_hex(value) if encoding == "hex_bytes" else _decode_u8_array(value)
        values = ", ".join(str(item) for item in data) or "0"
        expression = f"(const void *){variable}" if c_type == "const void *" else variable
        return expression, f"static const uint8_t {variable}[] = {{ {values} }};\n"
    raise ValueError(f"C oracle argument encoding {encoding} is unsupported")


def _require_scalar_type(c_type: str, encoding: str) -> None:
    if c_type not in INTEGER_C_TYPES.get(encoding, set()):
        raise ValueError(f"C type {c_type} is incompatible with {encoding}")


def _scalar_literal(
    c_type: str, encoding: str, value: Any, pointer_width: int
) -> str:
    if encoding == "bool":
        if not isinstance(value, bool):
            raise ValueError("bool fixture value is invalid")
        return "true" if value else "false"
    bounds = {
        "u16": (0, 2**16 - 1, "ULL"),
        "u32": (0, 2**32 - 1, "ULL"),
        "u64": (0, 2**64 - 1, "ULL"),
        "usize": (0, 2**pointer_width - 1, "ULL"),
        "i32": (-(2**31), 2**31 - 1, "LL"),
    }
    minimum, maximum, suffix = bounds.get(encoding, (1, 0, ""))
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{encoding} fixture value is invalid")
    return f"(({c_type}){value}{suffix})"


def _decode_hex(value: Any) -> bytes:
    if (
        not isinstance(value, str)
        or len(value) > MAX_BUFFER_BYTES * 2
        or len(value) % 2
        or not re.fullmatch(r"[0-9a-fA-F]*", value)
    ):
        raise ValueError("hex fixture field is invalid")
    return bytes.fromhex(value)


def _decode_u8_array(value: Any) -> bytes:
    if (
        not isinstance(value, list)
        or len(value) > MAX_BUFFER_BYTES
        or any(
            isinstance(item, bool)
            or not isinstance(item, int)
            or not 0 <= item <= 255
            for item in value
        )
    ):
        raise ValueError("u8_array fixture field is invalid")
    return bytes(value)


def _normalize_c_type(value: Any) -> str:
    return " ".join(str(value or "").replace("*", " * ").split()).replace(" * ", " *")


def _target_pointer_width(spec: dict[str, Any]) -> int:
    candidates = [
        spec.get("build_profile", {}).get("target", {}).get("pointer_width"),
        spec.get("c_boundary", {})
        .get("target_abi_contract", {})
        .get("pointer_width"),
    ]
    declared = {item for item in candidates if item is not None}
    if len(declared) != 1 or next(iter(declared), None) not in {32, 64}:
        raise ValueError("C oracle renderer requires one consistent 32/64-bit pointer width")
    return int(next(iter(declared)))


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{label} identifier is invalid")
    return value


def _safe_ident(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9_]", "_", value)
    return result if result and not result[0].isdigit() else f"case_{result}"


def _require_printable_ascii(value: str, label: str, maximum_bytes: int) -> None:
    encoded = value.encode("utf-8")
    if (
        len(encoded) > maximum_bytes
        or any(byte < 0x20 or byte > 0x7E for byte in encoded)
    ):
        raise ValueError(f"{label} must be bounded printable ASCII")


def _c_string_literal(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


__all__ = [
    "render_c_oracle_call_plan",
    "validate_c_oracle_call_plan_harness",
]
