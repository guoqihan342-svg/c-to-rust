from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .call_continue_model import negative_partition_probe_source, reference_outputs
from .errors import ReporterError
from .negative_runtime import (
    add_command_artifacts,
    command_result_summary,
    command_summary,
    content_ref,
    ensure_contained,
    path_ref,
    run_command,
)


SCENARIOS = (
    ("comparison-equality-flip", re.compile(rb"(?<![=!<>])==(?!=)"), b"==", b"!=", "all"),
    ("continue-noop", re.compile(rb"\bcontinue;"), b"continue;", b"let _=();", "hit"),
)


def run_call_continue_negative_execution(
    context: Any, draft_path: Path, replay_test_path: Path, output_dir: Path
) -> dict[str, Any]:
    rustc = shutil.which("rustc")
    if rustc is None:
        raise ReporterError("rustc is required for generated-draft negative replay")
    original = draft_path.read_bytes()
    replay_test = replay_test_path.read_bytes()
    artifact_dir = output_dir.resolve() / "translation-carrier-runtime" / str(context.spec["slice_id"])
    ensure_contained(context.repo_root, artifact_dir, "negative output directory")
    artifacts: dict[Path, bytes] = {}
    scenarios: list[dict[str, Any]] = []
    for scenario_id, pattern, before, after, partition in SCENARIOS:
        scenarios.append(
            _run_scenario(
                context, rustc, original, replay_test, artifact_dir, artifacts,
                scenario_id, pattern, before, after, partition, draft_path,
            )
        )
    return {"scenarios": scenarios, "artifacts": artifacts}


def _run_scenario(
    context: Any,
    rustc: str,
    original: bytes,
    replay_test: bytes,
    artifact_dir: Path,
    artifacts: dict[Path, bytes],
    scenario_id: str,
    pattern: re.Pattern[bytes],
    before: bytes,
    after: bytes,
    partition: str,
    draft_path: Path,
) -> dict[str, Any]:
    matches = list(pattern.finditer(original))
    if len(matches) != 1 or matches[0].group() != before:
        raise ReporterError(f"{scenario_id} requires exactly one declared mutation site")
    start, end = matches[0].span()
    mutated = original[:start] + after + original[end:]
    if len(mutated) != len(original):
        raise ReporterError(f"{scenario_id} changed generated draft length")
    changed = [index for index, pair in enumerate(zip(original, mutated, strict=True)) if pair[0] != pair[1]]
    if not changed or min(changed) < start or max(changed) >= end:
        raise ReporterError(f"{scenario_id} changed bytes outside the declared mutation")
    expected_detected = _expected_case_ids(context, partition)
    stem = scenario_id
    with tempfile.TemporaryDirectory(prefix=f"c2r-{scenario_id}-") as temp_text:
        temp = Path(temp_text)
        aliases = {rustc: "rustc", str(temp): "<translation-carrier-negative>"}
        same_source = temp / "same.rs"
        same_exe = temp / "same.exe"
        same_source.write_bytes(mutated + b"\n" + replay_test)
        same_compile = run_command(
            [rustc, "--edition=2021", "--test", "--error-format=json", "-Aunused_assignments", str(same_source), "-o", str(same_exe)],
            aliases=aliases,
        )
        if same_compile["returncode"] != 0:
            diagnostics = same_compile["stderr"].decode("utf-8", errors="replace").strip()
            raise ReporterError(
                f"{scenario_id} same-replay mutation did not compile: {diagnostics}"
            )
        same_run = run_command([str(same_exe), "--nocapture"], aliases=aliases)
        if same_run["returncode"] == 0:
            raise ReporterError(f"{scenario_id} same generated replay unexpectedly passed")

        partition_source = temp / "partition.rs"
        partition_exe = temp / "partition.exe"
        partition_source.write_bytes(
            mutated + b"\n" + negative_partition_probe_source(context, scenario_id).encode("utf-8")
        )
        partition_compile = run_command(
            [rustc, "--edition=2021", "--test", "--error-format=json", "-Aunused_assignments", str(partition_source), "-o", str(partition_exe)],
            aliases=aliases,
        )
        if partition_compile["returncode"] != 0:
            diagnostics = partition_compile["stderr"].decode("utf-8", errors="replace").strip()
            raise ReporterError(
                f"{scenario_id} partition replay did not compile: {diagnostics}"
            )
        case_runs = []
        for index, case in enumerate(context.cases):
            test_name = f"__c2r_negative_{scenario_id.replace('-', '_')}_case_{index}"
            result = run_command(
                [str(partition_exe), "--exact", test_name, "--nocapture"], aliases=aliases
            )
            detected = result["returncode"] != 0
            expected = str(case["id"]) in expected_detected
            if detected != expected:
                raise ReporterError(
                    f"{scenario_id} detection partition drifted for fixture case {case['id']}"
                )
            case_runs.append({"case_id": case["id"], "test_name": test_name, "detected": detected, **result})

    mutated_sha = hashlib.sha256(mutated).hexdigest()
    original_sha = hashlib.sha256(original).hexdigest()
    mutated_path = artifact_dir / f"mutated-{scenario_id}-rust-draft.rs"
    artifacts[mutated_path] = mutated
    add_command_artifacts(artifacts, artifact_dir, f"{stem}-same-compile", same_compile)
    add_command_artifacts(artifacts, artifact_dir, f"{stem}-same-run", same_run)
    add_command_artifacts(artifacts, artifact_dir, f"{stem}-partition-compile", partition_compile)
    for index, result in enumerate(case_runs):
        add_command_artifacts(artifacts, artifact_dir, f"{stem}-case-{index}-run", result)
    return {
        "scenario_id": scenario_id,
        "mutation": {
            "operator_from": before.decode("ascii"),
            "operator_to": after.decode("ascii"),
            "mutation_count": 1,
            "byte_offset": start,
            "original_draft": path_ref(context.repo_root, draft_path, original_sha),
            "mutated_draft": content_ref(context.repo_root, mutated_path, mutated),
            "mutated_sha256": mutated_sha,
        },
        "expected_detected_case_ids": expected_detected,
        "same_generated_replay_harness": command_summary(
            context, artifact_dir, f"{stem}-same", same_compile, same_run,
            expected_run_failure=True,
        ),
        "partition_replay": {
            "compile": command_result_summary(
                context, artifact_dir, f"{stem}-partition-compile", partition_compile
            ),
            "case_runs": [
                {
                    "case_id": item["case_id"],
                    "test_name": item["test_name"],
                    "detected": item["detected"],
                    **command_result_summary(
                        context, artifact_dir, f"{stem}-case-{index}-run", item
                    ),
                }
                for index, item in enumerate(case_runs)
            ],
            "detected_case_ids": [item["case_id"] for item in case_runs if item["detected"]],
            "passed_case_ids": [item["case_id"] for item in case_runs if not item["detected"]],
        },
    }


def _expected_case_ids(context: Any, partition: str) -> list[str]:
    if partition == "all":
        return [str(case["id"]) for case in context.cases]
    return [
        str(case["id"])
        for case in context.cases
        if reference_outputs(case, context.contract)[context.contract["return"]["fixture_field"]]
    ]
