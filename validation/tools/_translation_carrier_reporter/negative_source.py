from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .contract import ReporterError
from .record_contract import (
    KIND as RECORD_KIND,
    negative_partition_probe_source as record_negative_partition_probe_source,
)
from .sequence_contract import KIND as SEQUENCE_KIND
from .sequence_model import (
    negative_partition_probe_source as sequence_negative_partition_probe_source,
)
from .source_binding import StaticContext
from .state_replay_negative import (
    negative_partition_probe_source as state_replay_partition_probe_source,
)


def bind_external_replay_context(
    context: StaticContext,
    draft_path: Path,
    candidate: bytes,
    temp: Path,
) -> bytes:
    from validation.tools.auto_migrate import (
        external_direct_callee_context,
        inject_external_callee_stubs,
        load_plan_call_expressions,
    )

    call_expressions = load_plan_call_expressions(
        draft_path.parent,
        str(context.spec["slice_id"]),
    )
    external_context = external_direct_callee_context(context.spec, call_expressions)
    if external_context["status"] == "blocked":
        raise ReporterError("generated Rust replay external callee context is blocked")
    if external_context["status"] != "recorded":
        return candidate

    candidate_path = temp / "mutated_external_replay_input.rs"
    candidate_path.write_bytes(candidate)
    inject_external_callee_stubs(candidate_path, external_context, context.spec)
    return candidate_path.read_bytes()


def partition_probe_source(context: StaticContext) -> str:
    state_probe = state_replay_partition_probe_source(context)
    if state_probe is not None:
        return state_probe
    if context.contract.get("kind") == SEQUENCE_KIND:
        return sequence_negative_partition_probe_source(context)
    if context.contract.get("kind") == RECORD_KIND:
        return record_negative_partition_probe_source(context)
    function_name = context.spec["function_name"]
    external = context.contract["external_callee"]
    inputs = context.contract["inputs"]
    output_field = context.contract["output_pointer"]["fixture_field"]
    return_field = context.contract["return"]["fixture_field"]
    count_field = external["call_count_output"]
    args_field = external["call_args_output"]
    tests = []
    for index, case in enumerate(context.cases):
        expected = case["expected_outputs"]
        input_values = [case[item["fixture_field"]] for item in inputs]
        expected_args = expected[args_field]
        expected_return = str(expected[return_field]).lower()
        tests.append(
            f"""
#[test]
fn __c2r_negative_partition_case_{index}() {{
    __c2r_scripted_external_set_return({case[external['return_fixture_field']]}u32);
    __c2r_scripted_external_reset_calls();
    let mut actual_out = [0u32; 1];
    let actual_return = {function_name}(
        {input_values[0]}u32, {input_values[1]}u32, {input_values[2]}usize, &mut actual_out,
    );
    assert_eq!(actual_out[0], {expected[output_field]}u32, "{rust_string(case['id'])} output drifted");
    assert_eq!(__c2r_scripted_external_call_count(), {expected[count_field]}usize, "{rust_string(case['id'])} call count drifted");
    assert_eq!(
        __c2r_scripted_external_call_args(),
        ({expected_args[0]}u32, {expected_args[1]}u32, {expected_args[2]}usize),
        "{rust_string(case['id'])} call args drifted",
    );
    assert_eq!(actual_return, {expected_return}, "{rust_string(case['id'])} comparison mutation not detected");
}}
"""
        )
    return "".join(tests)


def body_call_statement_pattern(callee_name: str) -> re.Pattern[bytes]:
    return re.compile(
        rb"(?m)^(?P<statement>[ \t]*(?:let[ \t]+_[ \t]*=[ \t]*)?"
        + re.escape(callee_name.encode("utf-8"))
        + rb"[ \t]*\([^;\r\n]*\)[ \t]*;[ \t]*)(?:\r)?$"
    )


def suppress_body_call_statement(
    source: bytes, callee_name: str
) -> tuple[bytes, int, int]:
    matches = list(body_call_statement_pattern(callee_name).finditer(source))
    if len(matches) != 1:
        raise ReporterError(
            "generated Rust draft must contain exactly one standalone body callee invocation"
        )
    start, end = matches[0].span("statement")
    width = end - start
    if width < 2:
        raise ReporterError("generated Rust body callee statement is too short to suppress")
    replacement = b"//" + (b"x" * (width - 2))
    mutated = source[:start] + replacement + source[end:]
    return mutated, start, end


def rust_string(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')
