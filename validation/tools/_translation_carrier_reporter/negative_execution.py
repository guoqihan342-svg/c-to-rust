from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .contract import ReporterError, behavior_fields
from .record_contract import (
    KIND as RECORD_KIND,
    negative_partition_probe_source as record_negative_partition_probe_source,
)
from .source_binding import StaticContext


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
    matches = list(COMPARISON_PATTERN.finditer(original))
    if len(matches) != 1:
        raise ReporterError("generated Rust draft must contain exactly one == comparison mutation site")
    match = matches[0]
    mutated = original[: match.start()] + b"!=" + original[match.end() :]
    if len(mutated) != len(original):
        raise ReporterError("comparison mutation changed generated draft length")
    changed = [index for index, pair in enumerate(zip(original, mutated, strict=True)) if pair[0] != pair[1]]
    if changed != [match.start()]:
        raise ReporterError("generated Rust draft changed outside the unique comparison mutation")

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
                raise ReporterError(f"comparison mutation was not detected by fixture case {case['id']}")
            case_runs.append(
                {
                    "case_id": case["id"],
                    "comparison_partition": (
                        "comparison_true" if case["expected_outputs"][return_field] else "comparison_false"
                    ),
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
    if not true_ids or not false_ids:
        raise ReporterError("actual negative replay must detect true and false comparison partitions")
    return {
        "mutation": {
            "operator_from": "==",
            "operator_to": "!=",
            "mutation_count": 1,
            "byte_offset": match.start(),
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
        },
        "artifacts": artifacts,
    }


def partition_probe_source(context: StaticContext) -> str:
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


def run_command(argv: list[str], *, aliases: dict[str, str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReporterError(f"negative replay command failed to execute: {exc}") from exc
    return {
        "argv": [stable_text(item, aliases) for item in argv],
        "returncode": completed.returncode,
        "stdout": stable_bytes(completed.stdout, aliases),
        "stderr": stable_bytes(completed.stderr, aliases),
    }


def stable_text(value: str, aliases: dict[str, str]) -> str:
    stable = value
    for source, replacement in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        variants = {source, source.replace("\\", "/"), source.replace("/", "\\")}
        for variant in variants:
            if variant:
                stable = stable.replace(variant, replacement)
    return stable


def stable_bytes(value: bytes, aliases: dict[str, str]) -> bytes:
    stable = stable_text(value.decode("utf-8", errors="replace"), aliases)
    return (stable.rstrip("\r\n") + ("\n" if stable else "")).encode("utf-8")


def add_command_artifacts(
    artifacts: dict[Path, bytes],
    artifact_dir: Path,
    stem: str,
    result: dict[str, Any],
) -> None:
    artifacts[artifact_dir / f"{stem}.stdout.log"] = result["stdout"]
    artifacts[artifact_dir / f"{stem}.stderr.log"] = result["stderr"]


def command_summary(
    context: StaticContext,
    artifact_dir: Path,
    stem: str,
    compile_result: dict[str, Any],
    run_result: dict[str, Any],
    *,
    expected_run_failure: bool,
) -> dict[str, Any]:
    return {
        "compile": command_result_summary(
            context, artifact_dir, f"{stem}-compile", compile_result
        ),
        "run": command_result_summary(context, artifact_dir, f"{stem}-run", run_result),
        "expected_run_failure": expected_run_failure,
    }


def command_result_summary(
    context: StaticContext,
    artifact_dir: Path,
    stem: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    stdout = result["stdout"]
    stderr = result["stderr"]
    return {
        "argv": result["argv"],
        "returncode": result["returncode"],
        "stdout": content_ref(context.repo_root, artifact_dir / f"{stem}.stdout.log", stdout),
        "stderr": content_ref(context.repo_root, artifact_dir / f"{stem}.stderr.log", stderr),
    }


def path_ref(root: Path, path: Path, sha256: str) -> dict[str, Any]:
    return {"path": path.resolve().relative_to(root).as_posix(), "sha256": sha256}


def content_ref(root: Path, path: Path, content: bytes) -> dict[str, Any]:
    return {
        "path": path.resolve().relative_to(root).as_posix(),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def ensure_contained(root: Path, path: Path, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ReporterError(f"{label} escapes repo root") from exc


def rust_string(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')
