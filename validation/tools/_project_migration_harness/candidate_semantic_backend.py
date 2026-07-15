from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
import re
import secrets
import tempfile
from typing import Any

from .artifacts import content_sha256
from .candidate_semantic_backend_inputs import (
    BackendInputs, SemanticBackendError, load_backend_inputs,
)
from .candidate_semantic_backend_project import (
    materialize_abi_project,
    materialize_behavior_project,
    materialize_unsafe_project,
    write_manifest,
)
from .candidate_semantic_backend_sandbox import (
    CapturedRun,
    SemanticSandbox,
    cargo_check_arguments,
    cargo_run_arguments,
)
from .rust_candidate_facts import derive_rust_metadata


_BEHAVIOR_LINE = re.compile(rb"([0-9]+):(-?[0-9]+)\n")
_LAYOUT_LINE = re.compile(rb"([a-z]+(?:-[0-9]+)?):([0-9]+):([0-9]+)\n")


def run_semantic_backend(
    gate_family: str, request: Mapping[str, Any], repository_root: Path,
) -> dict[str, Any]:
    inputs = load_backend_inputs(request, gate_family, repository_root)
    try:
        with tempfile.TemporaryDirectory(
            prefix="candidate-semantic-project-",
        ) as temporary:
            project = Path(temporary)
            if gate_family == "unsafe-alias":
                manifest = materialize_unsafe_project(inputs, project)
            elif gate_family == "abi-layout":
                manifest = materialize_abi_project(inputs, project)
            else:
                manifest = materialize_behavior_project(
                    inputs, project, secrets.token_bytes(32),
                )
            manifest_sha256 = write_manifest(project, manifest)
            sandbox = SemanticSandbox(inputs, project)
            if gate_family == "oracle-replay-diff":
                return _oracle_replay_diff(sandbox, manifest, manifest_sha256)
            if gate_family == "negative":
                return _negative(sandbox, manifest, manifest_sha256)
            if gate_family == "unsafe-alias":
                return _unsafe_alias(sandbox, inputs, manifest_sha256)
            if gate_family == "abi-layout":
                return _abi_layout(sandbox, manifest, manifest_sha256)
    except SemanticBackendError:
        raise
    except (OSError, UnicodeError, ValueError) as error:
        raise SemanticBackendError("semantic_backend_execution_failed") from error
    raise SemanticBackendError("semantic_gate_family_unsupported")


def _oracle_replay_diff(
    sandbox: SemanticSandbox, manifest: Mapping[str, Any], manifest_sha256: str,
) -> dict[str, Any]:
    expected_count = int(manifest["case_count"])
    oracle = _run_behavior(sandbox, "c-oracle", manifest_sha256)
    if oracle.returncode != 0:
        raise SemanticBackendError("semantic_c_oracle_execution_failed")
    expected = _behavior_records(oracle.stdout, expected_count)
    replay = _run_behavior(sandbox, "rust-replay", manifest_sha256)
    actual, crash_count = _replay_records(replay, expected_count)
    mismatches = _mismatches(expected, actual) if not crash_count else []
    diff = {
        "schema_version": 1, "case_count": expected_count,
        "mismatch_count": len(mismatches), "crash_count": crash_count,
        "mismatch_case_ids": mismatches,
        "c_oracle_evidence_sha256": _run_binding(oracle, expected),
        "rust_replay_evidence_sha256": _run_binding(replay, actual),
    }
    return {
        "case_count": expected_count,
        "mismatch_count": len(mismatches),
        "crash_count": crash_count,
        "c_oracle_sha256": diff["c_oracle_evidence_sha256"],
        "rust_replay_sha256": diff["rust_replay_evidence_sha256"],
        "diff_sha256": content_sha256(diff),
    }


def _negative(
    sandbox: SemanticSandbox, manifest: Mapping[str, Any], manifest_sha256: str,
) -> dict[str, Any]:
    expected_count = int(manifest["case_count"])
    oracle = _run_behavior(sandbox, "c-oracle", manifest_sha256)
    replay = _run_behavior(sandbox, "rust-replay", manifest_sha256)
    if oracle.returncode != 0:
        raise SemanticBackendError("semantic_c_oracle_execution_failed")
    expected = _behavior_records(oracle.stdout, expected_count)
    actual, crash_count = _replay_records(replay, expected_count)
    baseline_mismatches = _mismatches(expected, actual) if not crash_count else [0]
    negative = _run_behavior(sandbox, "rust-negative", manifest_sha256)
    mutated, mutation_crash_count = _replay_records(negative, expected_count)
    mutation_mismatches = (
        _mismatches(expected, mutated) if not mutation_crash_count else []
    )
    detected = not mutation_crash_count and mutation_mismatches == [0]
    unexpected = int(bool(baseline_mismatches) or not detected)
    mutation = {
        "schema_version": 2,
        "mutation_kind": "executed-first-result-wrapping-add-one",
        "mutated_case_id": 0,
        "baseline_mismatch_count": len(baseline_mismatches),
        "mutation_mismatch_case_ids": mutation_mismatches,
        "mutation_crash_count": mutation_crash_count,
        "mutation_detected": detected,
        "c_oracle_evidence_sha256": _run_binding(oracle, expected),
        "rust_replay_evidence_sha256": _run_binding(replay, actual),
        "rust_negative_evidence_sha256": _run_binding(negative, mutated),
        "stimulus_sha256": content_sha256(manifest["stimulus"]),
    }
    return {
        "case_count": 1,
        "unexpected_accept_count": unexpected,
        "mutation_manifest_sha256": content_sha256(mutation),
    }


def _unsafe_alias(
    sandbox: SemanticSandbox, inputs: BackendInputs, manifest_sha256: str,
) -> dict[str, Any]:
    run = sandbox.run(
        purpose="candidate-semantic-unsafe-alias",
        cargo_arguments=cargo_check_arguments(), input_sha256=manifest_sha256,
    )
    source = inputs.candidate_source.decode("utf-8")
    unsafe_count = int(derive_rust_metadata(source)["unsafe_count"])
    if run.returncode == 0:
        unproven = 0 if unsafe_count == 0 else unsafe_count
    elif b"unsafe" in run.stderr.lower():
        unsafe_count = max(1, unsafe_count)
        unproven = unsafe_count
    else:
        raise SemanticBackendError("semantic_unsafe_analysis_failed")
    ledger = {
        "schema_version": 1, "analysis": "rustc-forbid-unsafe-code",
        "unsafe_site_count": unsafe_count, "unproven_alias_count": unproven,
        "execution_evidence_sha256": run.evidence_sha256,
    }
    alias = {
        "schema_version": 1,
        "proof": "vacuous-safe-rust-no-unsafe-sites" if unproven == 0 else "unproven",
        "unsafe_ledger_sha256": content_sha256(ledger),
        "compiler_enforced": True,
    }
    return {
        "unsafe_site_count": unsafe_count,
        "unproven_alias_count": unproven,
        "unsafe_ledger_sha256": content_sha256(ledger),
        "alias_evidence_sha256": content_sha256(alias),
    }


def _abi_layout(
    sandbox: SemanticSandbox, manifest: Mapping[str, Any], manifest_sha256: str,
) -> dict[str, Any]:
    expected_count = int(manifest["check_count"])
    c_layout = sandbox.run(
        purpose="candidate-semantic-c-abi",
        cargo_arguments=cargo_run_arguments("c-oracle"),
        input_sha256=manifest_sha256,
    )
    if c_layout.returncode != 0:
        raise SemanticBackendError("semantic_c_abi_execution_failed")
    expected = _layout_records(c_layout.stdout, expected_count)
    rust_layout = sandbox.run(
        purpose="candidate-semantic-rust-abi",
        cargo_arguments=cargo_run_arguments("rust-replay"),
        input_sha256=manifest_sha256,
    )
    if rust_layout.returncode == 0:
        actual = _layout_records(rust_layout.stdout, expected_count)
        mismatch_count = len(_mismatches(expected, actual))
    else:
        actual = {}
        mismatch_count = expected_count
    c_evidence = _run_binding(c_layout, expected)
    rust_evidence = _run_binding(rust_layout, actual)
    return {
        "check_count": expected_count,
        "mismatch_count": mismatch_count,
        "c_layout_sha256": c_evidence,
        "rust_layout_sha256": rust_evidence,
    }


def _run_behavior(
    sandbox: SemanticSandbox, binary: str, manifest_sha256: str,
) -> CapturedRun:
    return sandbox.run(
        purpose=f"candidate-semantic-{binary}",
        cargo_arguments=cargo_run_arguments(binary),
        input_sha256=manifest_sha256,
    )


def _behavior_records(data: bytes, expected_count: int) -> dict[int, int]:
    matches = list(_BEHAVIOR_LINE.finditer(data))
    if b"".join(item.group(0) for item in matches) != data:
        raise SemanticBackendError("semantic_behavior_output_invalid")
    result = {int(item.group(1)): int(item.group(2)) for item in matches}
    if len(result) != len(matches) or sorted(result) != list(range(expected_count)):
        raise SemanticBackendError("semantic_behavior_output_incomplete")
    return result


def _replay_records(run: CapturedRun, expected_count: int) -> tuple[dict[int, int], int]:
    if run.returncode != 0:
        return {}, 1
    try:
        return _behavior_records(run.stdout, expected_count), 0
    except SemanticBackendError:
        return {}, 1


def _layout_records(data: bytes, expected_count: int) -> dict[str, tuple[int, int]]:
    matches = list(_LAYOUT_LINE.finditer(data))
    if b"".join(item.group(0) for item in matches) != data:
        raise SemanticBackendError("semantic_layout_output_invalid")
    result = {
        item.group(1).decode("ascii"): (int(item.group(2)), int(item.group(3)))
        for item in matches
    }
    if len(result) != len(matches) or len(result) != expected_count:
        raise SemanticBackendError("semantic_layout_output_incomplete")
    return result


def _mismatches(left: Mapping[Any, Any], right: Mapping[Any, Any]) -> list[Any]:
    return sorted(key for key in set(left) | set(right) if left.get(key) != right.get(key))


def _run_binding(run: CapturedRun, records: Mapping[Any, Any]) -> str:
    return content_sha256({
        "execution": run.evidence,
        "records_sha256": content_sha256({str(key): value for key, value in records.items()}),
        "stdout_sha256": hashlib.sha256(run.stdout).hexdigest(),
    })


__all__ = ["run_semantic_backend"]
