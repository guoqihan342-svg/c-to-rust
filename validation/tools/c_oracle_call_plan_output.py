from __future__ import annotations

from pathlib import Path
from typing import Any

from validation.tools.c_oracle_call_plan_direct import (
    MAX_CASES,
    MAX_CASE_ID_BYTES,
    MAX_PROTOCOL_BYTES,
    MAX_RENDERED_BYTES,
    _c_string_literal,
    _matching_signature,
    _normalize_c_type,
    _render_argument,
    _require_printable_ascii,
    _require_scalar_type,
    _safe_ident,
    _scalar_literal,
    _target_pointer_width,
)
from validation.tools.c_oracle_output_protocol import (
    PROTOCOL_ID,
    protocol_printf_statement,
)
from validation.tools.c_oracle_call_plan_output_schema import (
    SCALAR_C_TYPES,
    abi_assertions,
    call_plan_sha,
    field_width_assertions,
    header_includes,
    observations as validate_observations,
    output_bindings,
    require_keys,
    validate_abi_contract,
)
from validation.tools.replay_call_plan import build_replay_call_plan
from validation.tools.replay_call_plan_fixture import _fixture_binding


def render_output_binding_call_plan(
    spec: dict[str, Any], repo_root: Path
) -> dict[str, Any]:
    plan = build_replay_call_plan(spec, repo_root)
    if plan.get("status") != "bound":
        return {
            "status": str(plan.get("status") or "unavailable"),
            "reason": str(plan.get("reason") or "bound ReplayCallPlan is unavailable"),
        }
    try:
        return _render(spec, plan, repo_root.resolve())
    except ValueError as exc:
        return {
            "status": "unavailable",
            "reason": str(exc),
            "replay_call_plan_sha256": plan.get("plan_sha256"),
        }


def _render(
    spec: dict[str, Any], plan: dict[str, Any], repo_root: Path
) -> dict[str, Any]:
    contract = spec.get("c_oracle_contract")
    require_keys(
        contract,
        {
            "schema_version",
            "kind",
            "abi",
            "headers",
            "output_bindings",
            "observations",
        },
        "C oracle contract",
    )
    if contract["schema_version"] != 1 or contract["kind"] != "direct_call_with_output_bindings":
        raise ValueError("C oracle output-binding contract identity is unsupported")
    validate_abi_contract(spec, contract["abi"])

    function_name = str(plan.get("source_function_name") or "")
    signature = _matching_signature(spec, function_name)
    parameters = signature["parameters"]
    by_name = {item["name"]: item for item in parameters}
    bindings = output_bindings(contract["output_bindings"], by_name)
    omitted = plan.get("omitted_c_parameters")
    if not isinstance(omitted, list) or set(omitted) != set(bindings):
        raise ValueError("C oracle output bindings must exactly close omitted C parameters")
    input_parameters = plan.get("parameters")
    if not isinstance(input_parameters, list):
        raise ValueError("ReplayCallPlan parameters are missing")
    by_c_parameter = {
        item.get("c_parameter"): item
        for item in input_parameters
        if isinstance(item, dict)
    }
    expected_inputs = set(by_name) - set(bindings)
    if set(by_c_parameter) != expected_inputs or len(by_c_parameter) != len(input_parameters):
        raise ValueError("ReplayCallPlan input parameter mapping is not closed")

    observations = validate_observations(
        contract["observations"], bindings, MAX_CASE_ID_BYTES
    )
    assertion_fields = [
        item.get("fixture_field")
        for item in plan.get("assertions") or []
        if isinstance(item, dict)
    ]
    observation_fields = [item["fixture_field"] for item in observations]
    if assertion_fields != observation_fields:
        raise ValueError("C observations must exactly match ReplayCallPlan assertions")
    behavior_fields = spec.get("fixture_contract", {}).get("observable_outputs")
    if behavior_fields != observation_fields:
        raise ValueError("C observations must exactly match fixture observable outputs")

    fixture = _fixture_binding(spec, repo_root)
    cases = fixture["cases"]
    if len(cases) > MAX_CASES:
        raise ValueError("C oracle call plan has too many fixture cases")
    pointer_width = _target_pointer_width(spec)
    call_plan_hash = call_plan_sha(spec, plan, contract)
    declarations = [f"/* COracleCallPlan-SHA256: {call_plan_hash} */\n"]
    declarations.extend(header_includes(spec, contract["headers"]))
    declarations.extend(abi_assertions(spec, pointer_width))
    declarations.extend(field_width_assertions(bindings, observations))
    declarations.append('static const char c2r_hex_digits[] = "0123456789abcdef";\n')
    statements: list[str] = []
    protocol_records: list[str] = []
    return_type = _normalize_c_type(signature.get("return_type"))
    for observation in observations:
        kind = observation["source"]["kind"]
        if kind == "return":
            _require_scalar_type(return_type, observation["encoding"])
        elif kind == "map_scalar" and return_type not in {"int", "int32_t"}:
            raise ValueError("mapped return C type is unsupported")

    for case_index, case in enumerate(cases):
        case_id = str(case.get("id") or f"case-{case_index}")
        _require_printable_ascii(case_id, "fixture case id", MAX_CASE_ID_BYTES)
        case_ident = _safe_ident(case_id)
        inputs = case.get("inputs")
        expected = case.get("expected")
        if not isinstance(inputs, dict) or not isinstance(expected, dict):
            raise ValueError(f"fixture case {case_id} is incomplete")
        arguments: list[str] = []
        binding_variables: dict[str, str] = {}
        for parameter in parameters:
            name = parameter["name"]
            if name in bindings:
                binding = bindings[name]
                variable = f"case_{case_ident}_{case_index}_{binding['id']}"
                binding_variables[binding["id"]] = variable
                statements.append(f"  {binding['c_type']} {variable} = {{0}};\n")
                arguments.append(f"&{variable}")
                continue
            expression, declaration = _render_argument(
                parameter,
                by_c_parameter[name],
                inputs,
                f"case_{case_ident}_{case_index}_{name}",
                pointer_width,
            )
            arguments.append(expression)
            if declaration:
                declarations.append(declaration)
        actual_return = f"actual_return_{case_ident}_{case_index}"
        statements.append(
            f"  {return_type} {actual_return} = {function_name}({', '.join(arguments)});\n"
        )
        for field_index, observation in enumerate(observations):
            field = observation["fixture_field"]
            if field not in expected:
                raise ValueError(f"fixture case {case_id} is missing expected field {field}")
            actual, setup = _render_observation(
                observation,
                binding_variables,
                actual_return,
                f"actual_{case_ident}_{case_index}_{field_index}",
            )
            statements.extend(setup)
            statements.extend(
                _comparison_statements(
                    observation["encoding"],
                    actual,
                    expected[field],
                    field,
                    pointer_width,
                )
            )
            protocol, record = protocol_printf_statement(
                call_plan_hash,
                case_index,
                case_id,
                field,
                observation["encoding"],
                expected[field],
                actual,
            )
            statements.append(protocol)
            protocol_records.append(record)

    declaration_text = "".join(declarations) + "\n"
    statement_text = "".join(statements)
    if len((declaration_text + statement_text).encode("utf-8")) > MAX_RENDERED_BYTES:
        raise ValueError("C oracle call-plan source exceeds the rendering limit")
    if len(("\n".join(protocol_records) + "\n").encode("utf-8")) > MAX_PROTOCOL_BYTES:
        raise ValueError("C oracle call-plan output protocol exceeds the capture limit")
    return {
        "status": "generated",
        "declarations": declaration_text,
        "statements": statement_text,
        "definitions_after_target": "",
        "replay_call_plan_sha256": plan["plan_sha256"],
        "c_oracle_call_plan_sha256": call_plan_hash,
        "case_count": len(cases),
        "compared_fields": observation_fields,
        "output_protocol": PROTOCOL_ID,
        "protocol_records": protocol_records,
    }


def _render_observation(
    observation: dict[str, Any],
    variables: dict[str, str],
    actual_return: str,
    actual: str,
) -> tuple[str, list[str]]:
    source = observation["source"]
    kind = source["kind"]
    encoding = observation["encoding"]
    if kind == "return":
        return actual_return, []
    if kind == "map_scalar":
        expression = _c_string_literal(str(source["default"]))
        for case in reversed(source["cases"]):
            expression = (
                f"({actual_return} == {case['equals']} ? "
                f"{_c_string_literal(str(case['value']))} : {expression})"
            )
        return actual, [f"  const char *{actual} = {expression};\n"]
    binding = variables[source["binding"]]
    field = binding + "." + ".".join(source["path"])
    if kind == "field":
        c_type = SCALAR_C_TYPES[encoding]
        return actual, [f"  {c_type} {actual} = ({c_type})({field});\n"]
    if kind == "be_u16":
        byte_ptr = f"{actual}_bytes"
        return actual, [
            f"  const uint8_t *{byte_ptr} = (const uint8_t *)&({field});\n",
            f"  uint16_t {actual} = (uint16_t)(((uint16_t){byte_ptr}[0] << 8) | {byte_ptr}[1]);\n",
        ]
    byte_ptr = f"{actual}_bytes"
    count = source["byte_count"]
    index = f"{actual}_index"
    return actual, [
        f"  const uint8_t *{byte_ptr} = (const uint8_t *)&({field});\n",
        f"  char {actual}[{count * 2 + 1}];\n",
        f"  for (size_t {index} = 0; {index} < {count}; ++{index}) {{\n",
        f"    {actual}[{index} * 2] = c2r_hex_digits[{byte_ptr}[{index}] >> 4];\n",
        f"    {actual}[{index} * 2 + 1] = c2r_hex_digits[{byte_ptr}[{index}] & 15];\n",
        "  }\n",
        f"  {actual}[{count * 2}] = '\\0';\n",
    ]


def _comparison_statements(
    encoding: str,
    actual: str,
    expected: Any,
    field: str,
    pointer_width: int,
) -> list[str]:
    if encoding in {"string", "hex_bytes"}:
        if not isinstance(expected, str):
            raise ValueError(f"{encoding} expected output is invalid")
        _require_printable_ascii(expected, "string expected output", 1024)
        condition = f"strcmp({actual}, {_c_string_literal(expected)}) != 0"
    else:
        c_type = SCALAR_C_TYPES[encoding]
        literal = _scalar_literal(c_type, encoding, expected, pointer_width)
        condition = f"{actual} != {literal}"
    return [
        f"  if ({condition}) {{\n",
        "    fprintf(stderr, " + _c_string_literal(f"{field} mismatch\\n") + ");\n",
        "    return 1;\n",
        "  }\n",
    ]


__all__ = ["render_output_binding_call_plan"]
