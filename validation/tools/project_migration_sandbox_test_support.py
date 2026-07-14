from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

from validation.tools import project_migration_legacy_cargo_test_support as integration
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract,
    SandboxRunResult,
    canonical_sha256,
)
from validation.tools._project_migration_harness.sandbox_diagnostics import (
    cargo_check_diagnostics,
)
from validation.tools._project_migration_harness.sandbox_requirements import (
    SandboxVerificationPlan, cargo_verification_plan,
    requirements_from_payload, strict_sandbox_requirements,
)
from validation.tools._project_migration_harness.sandbox_probe import (
    SandboxProbeReceipt, make_probe_receipt, validate_probe_receipt,
)


class BoundBackend:
    def __init__(self, *, tamper_contract: bool = False) -> None:
        self.contract = SandboxContract(
            backend="bubblewrap-v1",
            launcher_sha256="1" * 64,
            toolchain_sha256="2" * 64,
            requirements=strict_sandbox_requirements(cpu_seconds=60),
        )
        self.tamper_contract = tamper_contract
        self.calls: list[dict[str, object]] = []

    def execute(
        self,
        cargo_binary: Path,
        cargo_args: list[str],
        *,
        project_root: Path,
        runtime_root: Path,
        verification_plan: SandboxVerificationPlan,
        probe_receipt: object,
    ) -> SandboxRunResult:
        if not isinstance(probe_receipt, SandboxProbeReceipt):
            raise ValueError("test backend requires a sandbox probe receipt")
        validate_probe_receipt(
            probe_receipt, self.contract, verification_plan.requirements,
        )
        command = ["cargo", *cargo_args]
        self.calls.append({
            "cargo_binary": cargo_binary,
            "cargo_args": list(cargo_args),
            "project_root": project_root,
            "runtime_root": runtime_root,
            "timeout_seconds": verification_plan.timeout_seconds,
            "verification_plan_sha256": verification_plan.sha256,
        })
        return SandboxRunResult(
            completed=subprocess.CompletedProcess(command, 0, "", ""),
            contract_sha256=(
                "0" * 64 if self.tamper_contract else self.contract.sha256
            ),
            command_sha256=canonical_sha256(command),
            command_started=True,
            launcher_argv_sha256="3" * 64,
            requirements_sha256=self.contract.requirements.sha256,
            verification_plan_sha256=verification_plan.sha256,
            probe_receipt_sha256=probe_receipt.sha256,
        )


def managed_project(root: Path) -> tuple[Path, Path]:
    candidates = root / "candidates"
    candidates.mkdir()
    source = b"pub fn bounded_value() -> i32 { 7 }\n"
    source_path = candidates / "unit.rs"
    source_path.write_bytes(source)
    descriptor = {
        "group_id": "bounded-unit",
        "status": "accepted",
        "source_path": "unit.rs",
        "sha256": hashlib.sha256(source).hexdigest(),
        "public_symbols": ["bounded_value"],
        "required_symbols": [],
        "unsafe_count": 0,
    }
    project = root / "project"
    result = integration.integrate_candidates(
        {"dag": {"bounded-unit": []}}, [descriptor], candidates, project,
    )
    if result["status"] != "integrated":
        raise AssertionError(result)
    tools = root / "tools"
    tools.mkdir()
    cargo = tools / "cargo"
    cargo.write_bytes(b"host-owned-test-cargo")
    return project, cargo


def bind_execution_plan(
    execution: dict[str, object], input_sha256: str, *,
    timeout_seconds: int = 300,
) -> dict[str, object]:
    bound = deepcopy(execution)
    sandbox = bound.get("sandbox")
    checks = bound.get("checks")
    if not isinstance(sandbox, dict) or not isinstance(checks, list):
        raise AssertionError("test sandbox execution is invalid")
    contract = sandbox.get("contract")
    if not isinstance(contract, dict):
        raise AssertionError("test sandbox contract is invalid")
    requirements = requirements_from_payload(contract.get("requirements"))
    reopened_contract = SandboxContract(
        backend=str(contract.get("backend")),
        launcher_sha256=str(contract.get("launcher_sha256")),
        toolchain_sha256=str(contract.get("toolchain_sha256")),
        requirements=requirements,
    )
    probe = passing_probe_receipt(reopened_contract)
    sandbox["probe_receipt"] = probe.payload()
    sandbox["probe_receipt_sha256"] = probe.sha256
    sandbox["cleanup_verified"] = True
    for check in checks:
        if not isinstance(check, dict) or not isinstance(check.get("command"), list):
            raise AssertionError("test sandbox check is invalid")
        command = tuple(check["command"])
        plan = cargo_verification_plan(
            f"cargo-{command[1]}", command, input_sha256,
            timeout_seconds=timeout_seconds, requirements=requirements,
        )
        check["sandbox_requirements_sha256"] = requirements.sha256
        check["sandbox_command_started"] = True
        check["sandbox_verification_plan"] = plan.payload()
        check["sandbox_verification_plan_sha256"] = plan.sha256
        check["sandbox_probe_receipt_sha256"] = probe.sha256
        for stream in ("stdout", "stderr"):
            check[f"{stream}_sha256"] = hashlib.sha256(b"").hexdigest()
            check[f"{stream}_ref"] = None
            check[f"_captured_{stream}"] = ""
    return bound


def bind_cargo_output(
    check: dict[str, object], *, stdout: str, stderr: str = "",
) -> None:
    command = check.get("command")
    returncode = check.get("returncode")
    if (
        not isinstance(command, list) or len(command) < 2
        or command[1] not in {"check", "test"}
        or isinstance(returncode, bool) or not isinstance(returncode, int)
    ):
        raise AssertionError("test Cargo output binding is invalid")
    for stream, text in (("stdout", stdout), ("stderr", stderr)):
        check[f"{stream}_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        check[f"{stream}_ref"] = None
        check[f"_captured_{stream}"] = text
    check["diagnostics"] = cargo_check_diagnostics(
        stdout, str(command[1]), returncode,
    )


def cargo_compiler_message(
    *, code: str, message: str, file: str, line: int = 1, column: int = 1,
) -> str:
    return json.dumps({
        "reason": "compiler-message",
        "message": {
            "level": "error", "code": {"code": code}, "message": message,
            "spans": [{
                "is_primary": True, "file_name": f"/workspace/{file}",
                "line_start": line, "column_start": column,
            }],
        },
    }, sort_keys=True, separators=(",", ":")) + "\n"


def passing_probe_receipt(contract: SandboxContract) -> SandboxProbeReceipt:
    return make_probe_receipt(
        contract=contract, backend_version="test-only",
        capability_results={name: True for name in contract.requirements.capabilities},
        raw_observation={"fixture": "host-owned-test-probe"},
        cleanup_verified=True,
    )


def triples(values: list[str]) -> list[list[str]]:
    return [values[index:index + 3] for index in range(len(values) - 2)]


def executable(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    path.chmod(0o755)
    return path


def toolchain(root: Path, version: str) -> dict[str, Path]:
    binary_root = root / "bin"
    binary_root.mkdir(parents=True)
    library_root = root / "lib"
    library_root.mkdir()
    (library_root / "libstd.rlib").write_bytes(
        f"{version}-library".encode("ascii")
    )
    return {
        name: executable(binary_root / name, f"{version}-{name}".encode("ascii"))
        for name in ("cargo", "rustc", "rustdoc")
    }


__all__ = [
    "BoundBackend", "bind_cargo_output", "bind_execution_plan",
    "cargo_compiler_message", "executable", "managed_project",
    "passing_probe_receipt", "toolchain", "triples",
]
