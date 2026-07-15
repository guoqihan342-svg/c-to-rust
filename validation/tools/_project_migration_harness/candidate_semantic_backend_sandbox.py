from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from .artifacts import content_sha256
from .candidate_semantic_backend_inputs import BackendInputs, SemanticBackendError
from .sandbox_contract import contract_from_payload, validate_run_result
from .sandbox_linux import discover_sandbox_backend
from .sandbox_requirements import cargo_verification_plan


MAX_CAPTURE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class CapturedRun:
    returncode: int
    stdout: bytes
    stderr: bytes
    evidence: dict[str, Any]

    @property
    def evidence_sha256(self) -> str:
        return content_sha256(self.evidence)


class SemanticSandbox:
    def __init__(self, inputs: BackendInputs, project_root: Path) -> None:
        cargo_value = shutil.which("cargo")
        if not cargo_value:
            raise SemanticBackendError("semantic_cargo_unavailable")
        try:
            cargo = Path(cargo_value).resolve(strict=True)
            expected = contract_from_payload(inputs.sandbox_contract)
            discovery = discover_sandbox_backend(cargo, project_root)
        except (OSError, ValueError) as error:
            raise SemanticBackendError("semantic_sandbox_discovery_failed") from error
        if discovery.backend is None or discovery.probe_receipt is None:
            raise SemanticBackendError(
                discovery.reason_code or "semantic_sandbox_unavailable"
            )
        if discovery.backend.contract != expected or expected.native_linker is None:
            raise SemanticBackendError("semantic_compile_sandbox_contract_drifted")
        self._backend = discovery.backend
        self._probe_receipt = discovery.probe_receipt
        self._cargo = cargo
        self._project_root = project_root

    def run(
        self, *, purpose: str, cargo_arguments: tuple[str, ...],
        input_sha256: str, timeout_seconds: int = 120,
    ) -> CapturedRun:
        command = ("cargo", *cargo_arguments)
        plan = cargo_verification_plan(
            purpose, command, input_sha256,
            timeout_seconds=timeout_seconds,
            requirements=self._backend.contract.requirements,
        )
        try:
            with tempfile.TemporaryDirectory(
                prefix="candidate-semantic-runtime-",
            ) as temporary:
                runtime_root = Path(temporary)
                result = self._backend.execute(
                    self._cargo, cargo_arguments,
                    project_root=self._project_root,
                    runtime_root=runtime_root,
                    verification_plan=plan,
                    probe_receipt=self._probe_receipt,
                )
                validate_run_result(
                    result, self._backend.contract, plan,
                    self._probe_receipt,
                )
        except subprocess.TimeoutExpired as error:
            raise SemanticBackendError("semantic_sandbox_timeout") from error
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise SemanticBackendError("semantic_sandbox_execution_untrusted") from error
        stdout, stderr = result.completed.stdout, result.completed.stderr
        if (
            not isinstance(stdout, bytes) or not isinstance(stderr, bytes)
            or len(stdout) > MAX_CAPTURE_BYTES or len(stderr) > MAX_CAPTURE_BYTES
        ):
            raise SemanticBackendError("semantic_sandbox_output_too_large")
        evidence = {
            "schema_version": 1,
            "purpose": purpose,
            "input_sha256": input_sha256,
            "sandbox_contract_sha256": self._backend.contract.sha256,
            "sandbox_probe_receipt_sha256": self._probe_receipt.sha256,
            "verification_plan_sha256": plan.sha256,
            "command_sha256": result.command_sha256,
            "launcher_argv_sha256": result.launcher_argv_sha256,
            "command_started": result.command_started,
            "returncode": result.completed.returncode,
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
            "stdout_size_bytes": len(stdout),
            "stderr_size_bytes": len(stderr),
        }
        return CapturedRun(result.completed.returncode, stdout, stderr, evidence)


def cargo_run_arguments(binary: str) -> tuple[str, ...]:
    return (
        "run", "--offline", "--locked", "--quiet", "--manifest-path", "Cargo.toml",
        "--bin", binary,
    )


def cargo_check_arguments() -> tuple[str, ...]:
    return (
        "check", "--offline", "--locked", "--quiet", "--manifest-path", "Cargo.toml",
        "--lib",
    )


__all__ = [
    "CapturedRun", "SemanticSandbox", "cargo_check_arguments",
    "cargo_run_arguments",
]
