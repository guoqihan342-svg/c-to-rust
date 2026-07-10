from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .contract import ReporterError, behavior_fields
from .record_contract import (
    KIND as RECORD_KIND,
    negative_partition_probe_source as record_negative_partition_probe_source,
)
from .sequence_contract import KIND as SEQUENCE_KIND
from .sequence_model import (
    mutation_partition as sequence_mutation_partition,
    negative_partition_probe_source as sequence_negative_partition_probe_source,
)
from .source_binding import StaticContext
from .state_replay_kinds import is_state_replay_kind
from .state_replay_negative import (
    mutation_spec as state_replay_mutation_spec,
    negative_partition_probe_source as state_replay_partition_probe_source,
)
from .negative_runtime import (
    add_command_artifacts,
    command_result_summary,
    command_summary,
    content_ref,
    ensure_contained,
    path_ref,
    run_command,
)


COMPARISON_PATTERN = re.compile(rb"(?<![=!<>])==(?!=)")


def run_negative_execution(
    context: StaticContext,
    draft_path: Path,
    replay_test_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    rustc = shutil.which("rustc")
    if rustc is None:
        raise ReporterError("rustc is required for generated-draft negative replay")
    original = draft_path.read_bytes()
    state_mutation = state_replay_mutation_spec(context.contract)
    if state_mutation is not None:
        pattern, operator_from, operator_to = state_mutation
    elif context.contract.get("kind") == SEQUENCE_KIND:
        pattern = re.compile(rb"!=")
        operator_from = b"!="
        operator_to = b"=="
    else:
        pattern = COMPARISON_PATTERN
        operator_from = b"=="
        operator_to = b"!="
    matches = list(pattern.finditer(original))
    if len(matches) != 1:
        raise ReporterError(
            "generated Rust draft must contain exactly one declared mutation site"
        )
    match = matches[0]
    mutation_start, mutation_end = (
        match.span("value") if "value" in pattern.groupindex else match.span()
    )
    if original[mutation_start:mutation_end] != operator_from:
        raise ReporterError("declared mutation pattern did not select the expected operator")
    mutated = original[:mutation_start] + operator_to + original[mutation_end:]
    if len(mutated) != len(original):
        raise ReporterError("declared mutation changed generated draft length")
    changed = [index for index, pair in enumerate(zip(original, mutated, strict=True)) if pair[0] != pair[1]]
    if not changed or min(changed) < mutation_start or max(changed) >= mutation_end:
        raise ReporterError("generated Rust draft changed outside the unique declared mutation")

    output_root = output_dir.resolve()
    ensure_contained(context.repo_root, output_root, "negative output directory")
    artifact_dir = output_root / "translation-carrier-runtime" / str(context.spec["slice_id"])
    replay_test = replay_test_path.read_bytes()
    artifacts: dict[Path, bytes] = {}
    with tempfile.TemporaryDirectory(prefix="translation-carrier-negative-") as temp_text:
        temp = Path(temp_text)
        command_aliases = {
            rustc: "rustc",
            str(temp): "<translation-carrier-negative>",
        }
        same_source = temp / "mutated_same_replay.rs"
        same_exe = temp / "mutated_same_replay.exe"
        same_source.write_bytes(mutated + b"\n" + replay_test)
        same_compile = run_command(
            [rustc, "--edition=2021", "--test", "--error-format=json", str(same_source), "-o", str(same_exe)],
            aliases=command_aliases,
        )
        if same_compile["returncode"] != 0:
            raise ReporterError("mutated generated Rust replay did not compile")
        same_run = run_command([str(same_exe), "--nocapture"], aliases=command_aliases)
        if same_run["returncode"] == 0:
            raise ReporterError("mutated generated Rust replay unexpectedly passed")

        partition_source = temp / "mutated_partition_replay.rs"
        partition_exe = temp / "mutated_partition_replay.exe"
        partition_source.write_bytes(mutated + b"\n" + partition_probe_source(context).encode("utf-8"))
        partition_compile = run_command(
            [
                rustc,
                "--edition=2021",
                "--test",
                "--error-format=json",
                str(partition_source),
                "-o",
                str(partition_exe),
            ],
            aliases=command_aliases,
        )
        if partition_compile["returncode"] != 0:
            raise ReporterError("mutated partition replay did not compile")

        case_runs = []
        return_field = behavior_fields(context.contract)[0]
        for index, case in enumerate(context.cases):
            test_name = f"__c2r_negative_partition_case_{index}"
            result = run_command(
                [str(partition_exe), "--exact", test_name, "--nocapture"],
                aliases=command_aliases,
            )
            if result["returncode"] == 0:
                raise ReporterError(f"declared mutation was not detected by fixture case {case['id']}")
            comparison_partition = (
                sequence_mutation_partition(case, context.contract)
                if context.contract.get("kind") == SEQUENCE_KIND
                else "observable_mismatch"
                if is_state_replay_kind(context.contract)
                else (
                    "comparison_true"
                    if case["expected_outputs"][return_field]
                    else "comparison_false"
                )
            )
            case_runs.append(
                {
                    "case_id": case["id"],
                    "comparison_partition": comparison_partition,
                    "test_name": test_name,
                    **result,
                }
            )

    original_sha = hashlib.sha256(original).hexdigest()
    mutated_sha = hashlib.sha256(mutated).hexdigest()
    if original_sha == mutated_sha:
        raise ReporterError("comparison mutation did not change generated draft sha256")
    artifacts[artifact_dir / "mutated-rust-draft.rs"] = mutated
    add_command_artifacts(artifacts, artifact_dir, "same-replay-compile", same_compile)
    add_command_artifacts(artifacts, artifact_dir, "same-replay-run", same_run)
    add_command_artifacts(artifacts, artifact_dir, "partition-replay-compile", partition_compile)
    for index, result in enumerate(case_runs):
        add_command_artifacts(artifacts, artifact_dir, f"partition-case-{index}-run", result)

    true_ids = [item["case_id"] for item in case_runs if item["comparison_partition"] == "comparison_true"]
    false_ids = [item["case_id"] for item in case_runs if item["comparison_partition"] == "comparison_false"]
    if context.contract.get("kind") != SEQUENCE_KIND and not is_state_replay_kind(context.contract) and (
        not true_ids or not false_ids
    ):
        raise ReporterError("actual negative replay must detect true and false comparison partitions")
    exhausted_ids = [
        item["case_id"]
        for item in case_runs
        if item["comparison_partition"] == "sequence_exhaustion"
    ]
    mismatch_ids = [
        item["case_id"]
        for item in case_runs
        if item["comparison_partition"] == "observable_mismatch"
    ]
    return {
        "mutation": {
            "operator_from": operator_from.decode("ascii"),
            "operator_to": operator_to.decode("ascii"),
            "mutation_count": 1,
            "byte_offset": mutation_start,
            "original_draft": path_ref(context.repo_root, draft_path, original_sha),
            "mutated_draft": content_ref(
                context.repo_root,
                artifact_dir / "mutated-rust-draft.rs",
                mutated,
            ),
        },
        "same_generated_replay_harness": command_summary(
            context,
            artifact_dir,
            "same-replay",
            same_compile,
            same_run,
            expected_run_failure=True,
        ),
        "partition_replay": {
            "compile": command_result_summary(
                context, artifact_dir, "partition-replay-compile", partition_compile
            ),
            "case_runs": [
                {
                    "case_id": item["case_id"],
                    "comparison_partition": item["comparison_partition"],
                    "test_name": item["test_name"],
                    **command_result_summary(
                        context,
                        artifact_dir,
                        f"partition-case-{index}-run",
                        item,
                    ),
                }
                for index, item in enumerate(case_runs)
            ],
            "comparison_true_case_ids": true_ids,
            "comparison_false_case_ids": false_ids,
            "sequence_exhaustion_case_ids": exhausted_ids,
            "observable_mismatch_case_ids": mismatch_ids,
        },
        "artifacts": artifacts,
    }


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


def rust_string(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')
