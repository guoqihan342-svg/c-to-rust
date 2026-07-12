from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any


PROTOCOL_ID = "c2r_c_oracle_json_v1"
PROTOCOL_PREFIX = "C2R_C_ORACLE_JSON "
TOP_LEVEL_KEYS = {
    "case_id",
    "case_ordinal",
    "kind",
    "outputs",
    "plan_sha256",
    "schema_version",
}


def protocol_record(
    plan_sha256: str,
    case_ordinal: int,
    case_id: str,
    field: str,
    encoding: str,
    value: str,
) -> str:
    payload = {
        "schema_version": 1,
        "kind": "case_result",
        "plan_sha256": plan_sha256,
        "case_ordinal": case_ordinal,
        "case_id": case_id,
        "outputs": {field: {"encoding": encoding, "value": value}},
    }
    return PROTOCOL_PREFIX + json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )


def protocol_printf_statement(
    plan_sha256: str,
    case_ordinal: int,
    case_id: str,
    field: str,
    encoding: str,
    expected_value: Any,
    actual_expression: str,
) -> tuple[str, str]:
    if encoding == "bool":
        if not isinstance(expected_value, bool):
            raise ValueError("bool protocol value is invalid")
        value = "true" if expected_value else "false"
        placeholder = "%s"
        argument = f'({actual_expression} ? "true" : "false")'
    else:
        if isinstance(expected_value, bool) or not isinstance(expected_value, int):
            raise ValueError("integer protocol value is invalid")
        value = str(expected_value)
        if encoding == "i32":
            placeholder = "%lld"
            argument = f"(long long){actual_expression}"
        else:
            placeholder = "%llu"
            argument = f"(unsigned long long){actual_expression}"
    expected = protocol_record(
        plan_sha256, case_ordinal, case_id, field, encoding, value
    )
    format_text = (
        PROTOCOL_PREFIX
        + '{"case_id":'
        + _printf_json_string(case_id)
        + f',"case_ordinal":{case_ordinal},"kind":"case_result","outputs":{{'
        + _printf_json_string(field)
        + ':{"encoding":'
        + _printf_json_string(encoding)
        + f',"value":"{placeholder}"}}}},"plan_sha256":'
        + _printf_json_string(plan_sha256)
        + ',"schema_version":1}'
    )
    statement = f"  printf({json.dumps(format_text + chr(10))}, {argument});\n"
    return statement, expected


def _printf_json_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True).replace("%", "%%")


def c_oracle_call_plan_output_gate(
    rendered: Mapping[str, Any],
    fixture_binding: Mapping[str, Any] | None,
    harness_execution: Mapping[str, Any],
) -> dict[str, Any]:
    expected = list(rendered.get("protocol_records") or [])
    observed, invalid = _parse_protocol_lines(str(harness_execution.get("stdout") or ""))
    base = {
        "schema_version": 2,
        "gate": "c_oracle_harness_output",
        "protocol": PROTOCOL_ID,
        "semantic_pass": False,
        "plan_sha256": rendered.get("replay_call_plan_sha256"),
        "compared_fields": list(rendered.get("compared_fields") or []),
        "fixture_expected_output_status": str(
            fixture_binding.get("expected_output_status", "missing_or_empty")
            if isinstance(fixture_binding, Mapping)
            else "missing_or_empty"
        ),
        "expected_stdout_fragments": expected,
        "matched_stdout_fragments": [],
        "missing_stdout_fragments": expected,
        "observed_protocol_records": observed,
        "invalid_protocol_records": invalid,
        "unexpected_protocol_records": [item for item in observed if item not in expected],
        "boundary": (
            "Strict records prove execution of regenerated draft assertions only; "
            "accepted C/Rust diff gates remain required for semantic pass."
        ),
    }
    if (
        harness_execution.get("status") != "exited_zero_not_oracle"
        or harness_execution.get("returncode") != 0
    ):
        return {
            **base,
            "status": "not_run_not_oracle",
            "diagnostics": ["C oracle strict output protocol did not exit zero."],
        }
    if not expected:
        return {
            **base,
            "status": "unsupported_not_oracle",
            "diagnostics": ["C oracle call plan has no strict output records."],
        }
    if not invalid and observed == expected:
        return {
            **base,
            "status": "matched_not_oracle",
            "matched_stdout_fragments": expected,
            "missing_stdout_fragments": [],
            "unexpected_protocol_records": [],
            "diagnostics": [
                "C oracle strict output records matched exactly; semantic diff gates remain required."
            ],
        }
    return {
        **base,
        "status": "mismatch_not_oracle",
        "matched_stdout_fragments": [
            item
            for index, item in enumerate(expected)
            if index < len(observed) and observed[index] == item
        ],
        "missing_stdout_fragments": [item for item in expected if item not in observed],
        "diagnostics": [
            "C oracle strict output records were malformed, missing, duplicated, reordered, or unexpected."
        ],
    }


def validate_c_oracle_call_plan_output_gate(
    spec: dict[str, Any],
    contract: Any,
    harness_execution: Any,
    repo_root: Path,
    fixture_binding: Any = None,
) -> None:
    if not isinstance(contract, Mapping) or contract.get("status") == "not_used":
        return
    if contract.get("status") != "generated":
        raise ValueError("C oracle call-plan contract status is invalid")
    if not isinstance(harness_execution, Mapping):
        raise ValueError("C oracle harness execution is missing")
    from validation.tools.c_oracle_call_plan import render_c_oracle_call_plan

    rendered = render_c_oracle_call_plan(spec, repo_root)
    if rendered.get("status") != "generated":
        raise ValueError("C oracle strict output plan cannot be regenerated")
    gate = harness_execution.get("output_gate")
    if not isinstance(gate, Mapping):
        raise ValueError("C oracle strict output gate is missing")
    expected = c_oracle_call_plan_output_gate(
        rendered,
        fixture_binding if isinstance(fixture_binding, Mapping) else None,
        harness_execution,
    )
    if dict(gate) != expected:
        raise ValueError("C oracle strict output gate drifted from captured stdout")


def _parse_protocol_lines(stdout: str) -> tuple[list[str], list[str]]:
    observed: list[str] = []
    invalid: list[str] = []
    for line in stdout.splitlines():
        if not line.startswith(PROTOCOL_PREFIX):
            continue
        raw = line[len(PROTOCOL_PREFIX) :]
        try:
            payload = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
            _validate_payload(payload)
            canonical = PROTOCOL_PREFIX + json.dumps(
                payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
            )
            if canonical != line:
                raise ValueError("protocol JSON is not canonical")
            observed.append(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            invalid.append(line)
    return observed, invalid


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _validate_payload(payload: Any) -> None:
    if not isinstance(payload, dict) or set(payload) != TOP_LEVEL_KEYS:
        raise ValueError("protocol top-level keys are invalid")
    if payload.get("schema_version") != 1 or payload.get("kind") != "case_result":
        raise ValueError("protocol identity is invalid")
    if not isinstance(payload.get("case_ordinal"), int) or payload["case_ordinal"] < 0:
        raise ValueError("protocol case ordinal is invalid")
    for key in ("case_id", "plan_sha256"):
        if not isinstance(payload.get(key), str) or not payload[key]:
            raise ValueError(f"protocol {key} is invalid")
    outputs = payload.get("outputs")
    if not isinstance(outputs, dict) or len(outputs) != 1:
        raise ValueError("protocol outputs are invalid")
    output = next(iter(outputs.values()))
    if (
        not isinstance(output, dict)
        or set(output) != {"encoding", "value"}
        or not isinstance(output.get("encoding"), str)
        or not isinstance(output.get("value"), str)
    ):
        raise ValueError("protocol output record is invalid")


__all__ = [
    "PROTOCOL_ID",
    "c_oracle_call_plan_output_gate",
    "protocol_printf_statement",
    "protocol_record",
    "validate_c_oracle_call_plan_output_gate",
]
