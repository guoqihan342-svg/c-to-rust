from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path, content_sha256
from .candidate_semantic_evidence import (
    current_semantic_context,
    derive_semantic_status,
)
from .candidate_semantic_schema import (
    FIXED_RESOURCE_LIMITS,
    MAX_ADAPTER_OUTPUT_BYTES,
    SEMANTIC_FAMILIES,
    fixed_adapter_plan,
    parse_adapter_observation,
    semantic_raw_payload,
)
from .gate_authority import candidate_authority, candidate_verdict_payload
from .gate_evidence import write_content_addressed_json
from .ledger import LedgerError, ProjectLedger
from .sandbox_contract import canonical_sha256


@dataclass(frozen=True)
class _AdapterExecution:
    command_started: bool
    returncode: int | None
    timed_out: bool
    stdout: bytes
    stderr: bytes


def run_oracle_replay_diff_candidate(**kwargs: Any) -> dict[str, Any]:
    return _run_candidate_semantic("oracle-replay-diff", **kwargs)


def run_negative_candidate(**kwargs: Any) -> dict[str, Any]:
    return _run_candidate_semantic("negative", **kwargs)


def run_unsafe_alias_candidate(**kwargs: Any) -> dict[str, Any]:
    return _run_candidate_semantic("unsafe-alias", **kwargs)


def run_abi_layout_candidate(**kwargs: Any) -> dict[str, Any]:
    return _run_candidate_semantic("abi-layout", **kwargs)


def _run_candidate_semantic(
    gate_family: str, *, ledger: ProjectLedger, out_root: Path,
    out_root_rel: str, run_id: str, unit_id: str,
    candidate_artifact_id: str, verification_scope: str = "wave-provisional",
) -> dict[str, Any]:
    context, repository_root = current_semantic_context(
        ledger, run_id, unit_id, candidate_artifact_id, verification_scope,
    )
    _require_out_root(out_root, out_root_rel, repository_root)
    plan = fixed_adapter_plan(gate_family)
    request = canonical_json_bytes({
        "schema_version": 1,
        "artifact_kind": "candidate-semantic-adapter-request",
        "bindings": context,
        "verification_plan": plan,
    })
    execution = _invoke_fixed_adapter(plan, request, repository_root)
    blocked = _execution_blocker(execution)
    if blocked:
        return _blocked(context, gate_family, blocked)
    try:
        observation = parse_adapter_observation(execution.stdout, gate_family)
        execution_payload = _execution_payload(execution, plan)
        raw = semantic_raw_payload(
            gate_family=gate_family, context=context,
            execution=execution_payload, observation=observation,
        )
    except LedgerError:
        return _blocked(context, gate_family, "semantic_adapter_output_untrusted")
    refreshed, refreshed_root = current_semantic_context(
        ledger, run_id, unit_id, candidate_artifact_id, verification_scope,
    )
    if refreshed != context or refreshed_root != repository_root:
        raise LedgerError("candidate semantic verification context became stale")
    gate_status = _derive(raw, gate_family)
    raw_ref = _write_reference(
        out_root, out_root_rel, f"raw/candidate/{gate_family}", raw,
    )
    diagnostics = [] if gate_status == "passed" else [{
        "code": f"{gate_family}-observation-failed", "stage": gate_family,
    }]
    verdict = candidate_verdict_payload(
        run_id=run_id, unit_id=unit_id,
        candidate_artifact_id=candidate_artifact_id,
        candidate_sha256=str(context["candidate_sha256"]),
        gate_family=gate_family, status=gate_status, diagnostics=diagnostics,
        candidate_set_sha256=str(context["candidate_set_sha256"]),
        source_evidence=[raw_ref],
    )
    verdict_ref = _write_reference(
        out_root, out_root_rel, f"candidate/{gate_family}", verdict,
    )
    record_id = "host-semantic-" + content_sha256({
        "gate_family": gate_family,
        "verification_context_sha256": raw["verification_context_sha256"],
        "observation_sha256": raw_ref["sha256"],
    })[:24]
    ledger._record_derived_verification(
        record_id=record_id, run_id=run_id, unit_id=unit_id,
        candidate_artifact_id=candidate_artifact_id, kind="verifier",
        status=gate_status, verifier_id=candidate_authority(gate_family),
        evidence_path=str(verdict_ref["path"]),
        evidence_sha256=str(verdict_ref["sha256"]), gate_family=gate_family,
        metadata={
            "schema_version": 2,
            "candidate_set_sha256": context["candidate_set_sha256"],
            "verification_context_sha256": raw["verification_context_sha256"],
            "generation_sha256": context["generation_sha256"],
            "toolchain_sha256": context["toolchain_sha256"],
        },
    )
    if gate_status == "failed":
        ledger.mark_verification_failed(
            run_id=run_id, unit_id=unit_id,
            candidate_artifact_id=candidate_artifact_id,
            failed_record_id=record_id,
        )
    return {
        "schema_version": 1, "status": gate_status, "gate_status": gate_status,
        "run_id": run_id, "unit_id": unit_id,
        "candidate_artifact_id": candidate_artifact_id,
        "candidate_set_sha256": context["candidate_set_sha256"],
        "verification_scope": verification_scope, "record_id": record_id,
        "observation": raw_ref, "verdict": verdict_ref,
        "candidate_gate_recorded": True, "semantic_gate": False,
    }


def _invoke_fixed_adapter(
    plan: Mapping[str, Any], request: bytes, repository_root: Path,
) -> _AdapterExecution:
    if os.name != "posix":
        return _AdapterExecution(False, None, False, b"", b"POSIX resource isolation required")
    launcher = Path(sys.executable).resolve(strict=True)
    argv = [str(launcher), *plan["command"][1:]]
    if canonical_sha256(argv) != plan["launcher_argv_sha256"]:
        return _AdapterExecution(False, None, False, b"", b"adapter launch binding drifted")
    try:
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen(
                argv, cwd=repository_root, env={"PYTHONHASHSEED": "0", "PYTHONUTF8": "1"},
                stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, shell=False,
                preexec_fn=_apply_resource_limits,
            )
            try:
                process.communicate(input=request, timeout=int(plan["timeout_seconds"]))
                timed_out = False
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                timed_out = True
            stdout.seek(0); stderr.seek(0)
            return _AdapterExecution(
                True, process.returncode, timed_out,
                stdout.read(MAX_ADAPTER_OUTPUT_BYTES + 1),
                stderr.read(MAX_ADAPTER_OUTPUT_BYTES + 1),
            )
    except OSError as error:
        return _AdapterExecution(False, None, False, b"", str(error).encode("utf-8")[:1024])


def _apply_resource_limits() -> None:
    import resource
    keys = {
        "cpu_seconds": resource.RLIMIT_CPU,
        "address_space_bytes": resource.RLIMIT_AS,
        "file_size_bytes": resource.RLIMIT_FSIZE,
        "process_count": resource.RLIMIT_NPROC,
        "open_files": resource.RLIMIT_NOFILE,
    }
    for name, resource_id in keys.items():
        value = FIXED_RESOURCE_LIMITS[name]
        resource.setrlimit(resource_id, (value, value))


def _execution_blocker(value: _AdapterExecution) -> str | None:
    if not value.command_started:
        return "semantic_adapter_unavailable"
    if value.timed_out:
        return "semantic_adapter_timeout"
    if value.returncode != 0:
        return "semantic_adapter_process_failed"
    if len(value.stdout) > MAX_ADAPTER_OUTPUT_BYTES or len(value.stderr) > MAX_ADAPTER_OUTPUT_BYTES:
        return "semantic_adapter_output_too_large"
    return None


def _execution_payload(value: _AdapterExecution, plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "command_sha256": plan["command_sha256"],
        "launcher_argv_sha256": plan["launcher_argv_sha256"],
        "command_started": value.command_started, "returncode": value.returncode,
        "timed_out": value.timed_out,
        "stdout_sha256": hashlib.sha256(value.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(value.stderr).hexdigest(),
        "stdout_size_bytes": len(value.stdout), "stderr_size_bytes": len(value.stderr),
    }


def _derive(raw: Mapping[str, Any], family: str) -> str:
    return derive_semantic_status(
        raw, run_id=str(raw["run_id"]), unit_id=str(raw["unit_id"]),
        candidate_artifact_id=str(raw["candidate_artifact_id"]),
        candidate_sha256=str(raw["candidate_sha256"]),
        candidate_set_sha256=str(raw["candidate_set_sha256"]), gate_family=family,
    )


def _write_reference(
    out_root: Path, out_root_rel: str, scope: str, payload: Mapping[str, Any],
) -> dict[str, Any]:
    reference = write_content_addressed_json(out_root, scope, payload)
    return {**reference, "path": f"{out_root_rel}/{reference['path']}"}


def _require_out_root(out_root: Path, out_root_rel: str, repository_root: Path) -> None:
    try:
        relative = checked_relative_path(out_root_rel)
        expected = repository_root.joinpath(*PurePosixPath(relative).parts).resolve(strict=True)
    except (OSError, ValueError) as error:
        raise LedgerError("candidate semantic output root is invalid") from error
    if out_root.resolve(strict=True) != expected:
        raise LedgerError("candidate semantic output root escapes the repository")


def _blocked(context: Mapping[str, Any], family: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1, "status": "blocked", "gate_family": family,
        "run_id": context["run_id"], "unit_id": context["unit_id"],
        "candidate_artifact_id": context["candidate_artifact_id"],
        "candidate_set_sha256": context["candidate_set_sha256"],
        "reason_code": reason, "candidate_gate_recorded": False,
        "semantic_gate": False,
    }


def _adapter_worker_main(gate_family: str) -> int:
    if gate_family not in SEMANTIC_FAMILIES:
        return 64
    data = sys.stdin.buffer.read(MAX_ADAPTER_OUTPUT_BYTES + 1)
    try:
        request = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return 65
    if not isinstance(request, dict) or canonical_json_bytes(request) != data:
        return 65
    sys.stderr.write("dedicated semantic adapter backend is not configured\n")
    return 78


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--adapter-worker":
        raise SystemExit(_adapter_worker_main(sys.argv[2]))
    raise SystemExit(64)


__all__ = [
    "run_abi_layout_candidate", "run_negative_candidate",
    "run_oracle_replay_diff_candidate", "run_unsafe_alias_candidate",
]
