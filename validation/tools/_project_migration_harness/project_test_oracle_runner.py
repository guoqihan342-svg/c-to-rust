from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .project_test_input_snapshot import materialize_project_test_input_snapshot
from .project_test_inventory_paths import expand_input_binding
from .project_test_oracle_binaries import (
    candidate_binaries, copy_oracle_binaries, tests_by_id,
)
from .project_test_oracle_evidence import (
    baseline_passed, build_project_oracle_evidence,
)
from .project_test_oracle_workspace import materialize_project_oracle_workspace
from .project_test_process_sandbox import public_process_result
from .project_test_stdin import read_snapshot_stdin
from .project_verification_execution import run_cargo_check
from .sandbox_linux import discover_sandbox_backend
from .sandbox_probe import SandboxProbeReceipt


def run_project_test_oracle(
    *, repo_root: Path, generation_root: Path, runtime_root: Path,
    rust_project_ir: Mapping[str, Any], inventory: Mapping[str, Any],
    mapping: Mapping[str, Any], excludes: Sequence[Path] = (),
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    del excludes  # The minimal input closure never snapshots unrelated repository paths.
    if not 30 <= timeout_seconds <= 3_600:
        raise ValueError("project_test_oracle_timeout_invalid")
    if inventory.get("status") != "ready" or mapping.get("status") != "ready":
        return _blocked("project_test_oracle_inputs_not_ready")
    if mapping.get("rust_project_ir_sha256") != rust_project_ir.get("ir_sha256"):
        return _blocked("project_test_oracle_ir_binding_drifted")
    try:
        cargo = _cargo_binary()
        discovery = discover_sandbox_backend(cargo, Path(generation_root))
    except (OSError, ValueError):
        return _blocked("project_test_oracle_sandbox_unavailable")
    backend = discovery.backend
    if (
        backend is None or not isinstance(discovery.probe_receipt, SandboxProbeReceipt)
        or not callable(getattr(backend, "execute_project_test_process", None))
    ):
        return _blocked(discovery.reason_code or "project_test_oracle_sandbox_unavailable")
    base = Path(runtime_root)
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    workspace = Path(tempfile.mkdtemp(prefix="project-oracle-workspace-", dir=base))
    execution = Path(tempfile.mkdtemp(prefix="project-oracle-runtime-", dir=base))
    try:
        result = _execute_oracle(
            cargo=cargo, backend=backend, probe_receipt=discovery.probe_receipt,
            repo_root=Path(repo_root), generation_root=Path(generation_root),
            workspace=workspace, execution=execution,
            rust_project_ir=rust_project_ir, inventory=inventory,
            mapping=mapping, timeout_seconds=timeout_seconds,
        )
    except (KeyError, OSError, TypeError, ValueError) as error:
        result = _blocked(str(error)[:96] or "project_test_oracle_execution_invalid")
    finally:
        cleanup_verified = _cleanup(workspace) and _cleanup(execution)
    if not cleanup_verified:
        return _result("blocked", "project_test_oracle_cleanup_failed")
    return {**result, "cleanup_verified": True}


def _execute_oracle(
    *, cargo: Path, backend: Any, probe_receipt: SandboxProbeReceipt,
    repo_root: Path, generation_root: Path, workspace: Path, execution: Path,
    rust_project_ir: Mapping[str, Any], inventory: Mapping[str, Any],
    mapping: Mapping[str, Any], timeout_seconds: int,
) -> dict[str, Any]:
    input_snapshot = materialize_project_test_input_snapshot(
        repo_root, execution / "input", inventory,
    )
    workspace_evidence = materialize_project_oracle_workspace(
        generation_root=generation_root, workspace_root=workspace,
        rust_project_ir=rust_project_ir, inventory=inventory, mapping=mapping,
    )
    build_runtime = execution / "build-runtime"
    for name in ("cargo-home", "target"):
        (build_runtime / name).mkdir(parents=True, mode=0o700)
    build = run_cargo_check(
        cargo, ["build", "--workspace", "--bins", "--offline", "--locked", "--quiet"],
        workspace, build_runtime, timeout_seconds, backend,
        str(mapping["mapping_sha256"]), probe_receipt, capture_raw_output=True,
    )
    build_output = _take_captured_output(build)
    if build.get("status") != "passed" or build.get("returncode") != 0:
        return _result(
            "failed" if build.get("status") == "failed" else "blocked",
            "project_test_oracle_cargo_build_failed", build=build,
            build_output=build_output, input_snapshot=input_snapshot,
            workspace=workspace_evidence,
        )
    tests = tests_by_id(inventory)
    mappings = {
        str(item["source_target_id"]): item for item in mapping["mappings"]
    }
    oracle_binaries = copy_oracle_binaries(
        repo_root, execution / "oracle-binaries", tests,
    )
    rust_binaries = candidate_binaries(build_runtime, mappings)
    oracle_results: dict[str, Mapping[str, Any]] = {}
    for test_id, test in tests.items():
        result = _run_case(
            backend, probe_receipt, oracle_binaries[test_id],
            execution / "input", execution / "oracle-runs" / test_id,
            test, input_snapshot, timeout_seconds,
        )
        oracle_results[test_id] = result
        if result.get("status") != "completed":
            return _blocked_with_execution(
                "project_test_oracle_baseline_execution_blocked", test_id,
                result, build, build_output, input_snapshot, workspace_evidence,
            )
        if not baseline_passed(result):
            return _blocked_with_execution(
                "project_test_oracle_baseline_failed", test_id, result,
                build, build_output, input_snapshot, workspace_evidence,
            )
    replay_results: dict[str, Mapping[str, Any]] = {}
    for test_id, test in tests.items():
        source_target = str(test["source_target_id"])
        result = _run_case(
            backend, probe_receipt, rust_binaries[source_target],
            execution / "input", execution / "replay-runs" / test_id,
            test, input_snapshot, timeout_seconds,
        )
        if result.get("status") == "blocked" and result.get("reason_code") not in {
            "project_test_process_timed_out", "project_test_process_output_too_large",
        }:
            return _blocked_with_execution(
                "project_test_replay_execution_blocked", test_id, result,
                build, build_output, input_snapshot, workspace_evidence,
            )
        replay_results[test_id] = result
    evidence = build_project_oracle_evidence(
        inventory=inventory, mapping=mapping,
        oracle_results=oracle_results, replay_results=replay_results,
    )
    mismatch_count = int(evidence["mismatch_count"])
    observation = {
        "case_count": int(evidence["case_count"]),
        "mismatch_count": mismatch_count,
        "crash_count": int(evidence["crash_count"]),
        "oracle_sha256": content_sha256({
            "inventory_sha256": inventory["inventory_sha256"],
            "mapping_sha256": mapping["mapping_sha256"],
            "input_snapshot_sha256": input_snapshot["snapshot_sha256"],
            "workspace_sha256": workspace_evidence["workspace_sha256"],
            "evidence_sha256": evidence["evidence_sha256"],
        }),
        "evidence_sha256": evidence["evidence_sha256"],
        "input_snapshot_sha256": input_snapshot["snapshot_sha256"],
        "candidate_sha256": str(rust_project_ir["ir_sha256"]),
        "execution_isolation": "independent-oracle-and-replay-sandboxes",
    }
    return {
        "schema_version": 2, "artifact_kind": "project-test-oracle-result",
        "status": "passed" if mismatch_count == 0 else "failed",
        "reason_code": None if mismatch_count == 0 else "project_test_logic_mismatch",
        "observation": observation, "evidence": evidence,
        "build": build, "build_output": build_output,
        "input_snapshot": input_snapshot, "workspace": workspace_evidence,
        "isolation": {
            "shared_read_only_input_snapshot": True,
            "shared_runtime_state": False,
            "source_executable_visible_to_replay": False,
            "comparison_authority": "trusted-host",
        },
        "cleanup_verified": False, "semantic_gate": False,
    }


def _run_case(
    backend: Any, probe_receipt: SandboxProbeReceipt, executable: Path,
    input_root: Path, runtime: Path, test: Mapping[str, Any],
    snapshot: Mapping[str, Any], timeout_seconds: int,
) -> dict[str, Any]:
    arguments = [
        expand_input_binding(item, guest_root="/workspace")
        for item in test["arguments"]
    ]
    environment = {
        str(key): expand_input_binding(value, guest_root="/workspace")
        for key, value in test["environment"].items()
    }
    standard_input = read_snapshot_stdin(
        input_root, test.get("stdin"), snapshot,
    )
    return backend.execute_project_test_process(
        executable, project_root=input_root, runtime_root=runtime,
        arguments=arguments, working_directory=str(test["working_directory"]),
        environment=environment,
        timeout_seconds=min(int(test["timeout_seconds"]), timeout_seconds),
        input_sha256=str(snapshot["snapshot_sha256"]),
        standard_input=standard_input,
        probe_receipt=probe_receipt,
    )


def _blocked_with_execution(
    code: str, test_id: str, execution: Mapping[str, Any],
    build: Mapping[str, Any], build_output: Mapping[str, Any],
    snapshot: Mapping[str, Any], workspace: Mapping[str, Any],
) -> dict[str, Any]:
    return _result(
        "blocked", code, test_id=test_id,
        process=public_process_result(execution), build=dict(build),
        build_output=dict(build_output), input_snapshot=dict(snapshot),
        workspace=dict(workspace),
    )


def _cargo_binary() -> Path:
    value = shutil.which("cargo")
    if not value:
        raise ValueError("project_test_oracle_cargo_unavailable")
    path = Path(value).resolve(strict=True)
    if path.name not in {"cargo", "rustup"} or not path.is_file():
        raise ValueError("project_test_oracle_cargo_untrusted")
    return path


def _take_captured_output(check: dict[str, Any]) -> dict[str, str]:
    stdout = check.pop("_captured_stdout", b"")
    stderr = check.pop("_captured_stderr", b"")
    return {
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stdout_prefix": _decode_prefix(stdout),
        "stderr_prefix": _decode_prefix(stderr),
    }


def _decode_prefix(value: Any) -> str:
    return value[:4096].decode("utf-8", errors="replace") if isinstance(value, bytes) else ""


def _cleanup(path: Path) -> bool:
    try:
        if path.is_symlink():
            return False
        shutil.rmtree(path)
        return not path.exists()
    except OSError:
        return False


def _blocked(code: str) -> dict[str, Any]:
    return _result("blocked", code)


def _result(status: str, code: str, **details: Any) -> dict[str, Any]:
    return {
        "schema_version": 2, "artifact_kind": "project-test-oracle-result",
        "status": status, "reason_code": code, "observation": None,
        "cleanup_verified": False, "semantic_gate": False, **details,
    }


__all__ = ["run_project_test_oracle"]
