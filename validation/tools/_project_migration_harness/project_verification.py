from __future__ import annotations

from pathlib import Path
import re
import tempfile
from typing import Any

from .anchored_artifact_io import open_directory_anchor
from .cargo_build_product_capture import capture_cargo_build_products
from .cargo_rustc_dep_info_capture import capture_cargo_rustc_dep_info
from .cargo_fact_commands import CARGO_BUILD_ARGS, CARGO_METADATA_ARGS
from .integration_generation import (
    GenerationCommitError,
)
from .integration_validation import existing_state
from .sandbox_contract import (
    validate_contract,
)
from .sandbox_linux import discover_sandbox_backend
from .sandbox_probe import (
    SandboxProbeReceipt, validate_probe_receipt,
)
from .project_verification_execution import (
    blocked_result as _blocked,
    environment_policy as _environment_policy,
    run_cargo_check as _run,
    sandbox_evidence as _sandbox_evidence,
)
from .project_verification_paths import (
    cargo_binary as _cargo_binary,
    cleanup_execution_root as _cleanup_execution_root,
    current_managed_source as _current_managed_source,
    is_linklike as _is_linklike,
    project_target as _project_target,
    runtime_root as _runtime_root,
    validate_capture_options as _validate_capture_options,
)
SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
def run_cargo_project_gates(
    project_root: Path, *, runtime_root: Path, cargo_command: str = "cargo",
    timeout_seconds: int = 300, capture_raw_output: bool = False,
    capture_native_link_trace: bool = False,
    capture_cargo_facts: bool = False,
    capture_cargo_structure: bool = False,
) -> dict[str, Any]:
    _validate_capture_options(
        timeout_seconds, capture_raw_output=capture_raw_output,
        capture_native_link_trace=capture_native_link_trace,
        capture_cargo_facts=capture_cargo_facts,
        capture_cargo_structure=capture_cargo_structure,
    )
    project = _project_target(project_root)
    try:
        source = _current_managed_source(project)
    except GenerationCommitError as error:
        return _blocked(
            "generation_recovery_blocked",
            project_input_sha256=None,
            detail=error.code,
        )
    return _run_managed_cargo(
        source, project, runtime_root, cargo_command, timeout_seconds,
        capture_raw_output, capture_native_link_trace, capture_cargo_facts,
        capture_cargo_structure,
    )
def run_cargo_generation_gates(
    generation_root: Path, *, runtime_root: Path, cargo_command: str = "cargo",
    timeout_seconds: int = 300, capture_raw_output: bool = False,
    capture_native_link_trace: bool = False,
    capture_cargo_facts: bool = False,
    capture_cargo_structure: bool = False,
) -> dict[str, Any]:
    _validate_capture_options(
        timeout_seconds, capture_raw_output=capture_raw_output,
        capture_native_link_trace=capture_native_link_trace,
        capture_cargo_facts=capture_cargo_facts,
        capture_cargo_structure=capture_cargo_structure,
    )
    source = _project_target(generation_root).resolve(strict=True)
    return _run_managed_cargo(
        source, source, runtime_root, cargo_command, timeout_seconds,
        capture_raw_output, capture_native_link_trace, capture_cargo_facts,
        capture_cargo_structure,
    )
def managed_project_input_sha256(project_root: Path) -> str:
    project = _project_target(project_root)
    source = _current_managed_source(project)
    state, managed = existing_state(source)
    if not managed or not isinstance(state, str) or SHA256.fullmatch(state) is None:
        raise ValueError(
            "Cargo project must be a managed last-good reconstruction with a SHA-256 state"
        )
    return state
def _run_managed_cargo(
    source: Path, project: Path, runtime_root: Path,
    cargo_command: str, timeout_seconds: int, capture_raw_output: bool,
    capture_native_link_trace: bool, capture_cargo_facts: bool,
    capture_cargo_structure: bool,
) -> dict[str, Any]:
    before, managed = existing_state(source)
    if not managed:
        raise ValueError("Cargo project must be a managed last-good reconstruction")
    runtime = _runtime_root(runtime_root, project, source)
    try:
        cargo = _cargo_binary(cargo_command)
    except (OSError, ValueError):
        return _blocked(
            "cargo_tool_unavailable",
            project_state=before,
            project_input_sha256=before,
        )
    discovery = discover_sandbox_backend(cargo, source)
    if discovery.backend is None:
        return _blocked(
            discovery.reason_code or "cargo_sandbox_unavailable",
            project_state=before,
            project_input_sha256=before,
        )
    backend = discovery.backend
    try:
        validate_contract(backend.contract)
    except ValueError:
        return _blocked(
            "sandbox_contract_invalid",
            project_state=before,
            project_input_sha256=before,
        )
    try:
        probe_receipt = discovery.probe_receipt
        if not isinstance(probe_receipt, SandboxProbeReceipt):
            raise ValueError("sandbox probe receipt is missing")
        validate_probe_receipt(
            probe_receipt, backend.contract, backend.contract.requirements,
        )
    except ValueError:
        return _blocked(
            "sandbox_capability_probe_invalid",
            project_state=before,
            project_input_sha256=before,
        )
    if (capture_native_link_trace or capture_cargo_structure) and backend.contract.native_linker is None:
        return _blocked(
            "sandbox_native_linker_unavailable",
            project_state=before,
            project_input_sha256=before,
        )
    execution_root = Path(tempfile.mkdtemp(prefix="cargo-sandbox-", dir=runtime))
    checks = []
    fact_probes: dict[str, dict[str, Any]] = {}
    structure_probes: dict[str, dict[str, Any]] = {}
    captured_products: list[dict[str, Any]] = []
    captured_dep_info: list[dict[str, Any]] = []
    product_capture_error = False
    target_anchor = None
    try:
        for name in ("cargo-home", "target"):
            (execution_root / name).mkdir(mode=0o700)
        if capture_cargo_structure:
            try:
                target_anchor = open_directory_anchor(execution_root / "target")
            except ValueError:
                product_capture_error = True
        if capture_cargo_facts:
            fact_probes["cargo-metadata"] = _run(
                cargo, list(CARGO_METADATA_ARGS), source, execution_root,
                timeout_seconds, backend, before, probe_receipt,
                capture_raw_output=True,
                native_link_trace=False,
            )
        metadata_ready = (
            not capture_cargo_facts
            or fact_probes["cargo-metadata"]["status"] == "passed"
        )
        if capture_cargo_structure and metadata_ready and not product_capture_error:
            structure_probes["cargo-build"] = _run(
                cargo, list(CARGO_BUILD_ARGS), source, execution_root,
                timeout_seconds, backend, before, probe_receipt,
                capture_raw_output=True, native_link_trace=True,
            )
            if structure_probes["cargo-build"]["status"] == "passed":
                try:
                    captured_products = capture_cargo_build_products(
                        structure_probes["cargo-build"], execution_root,
                        target_anchor=target_anchor,
                    )
                    captured_dep_info = capture_cargo_rustc_dep_info(
                        structure_probes["cargo-build"], execution_root,
                        target_anchor=target_anchor,
                    )
                except (KeyError, OSError, TypeError, ValueError):
                    product_capture_error = True
        commands = [
            (["check", "--all-targets", "--all-features", "--offline", "--locked",
              "--message-format=json"], False),
            (["test", "--all-targets", "--all-features", "--offline", "--locked",
              "--message-format=json", *(
                  ["--jobs", "1"] if capture_native_link_trace else []
              )], capture_native_link_trace),
        ]
        structure_ready = (
            not capture_cargo_structure
            or (
                structure_probes.get("cargo-build", {}).get("status") == "passed"
                and bool(captured_products) and not product_capture_error
            )
        )
        if metadata_ready and structure_ready:
            for cargo_args, native_link_trace in commands:
                checks.append(_run(
                    cargo, cargo_args, source, execution_root,
                    timeout_seconds, backend, before, probe_receipt,
                    capture_raw_output=capture_raw_output,
                    native_link_trace=native_link_trace,
                ))
                if checks[-1]["status"] != "passed":
                    break
        try:
            after, still_managed = existing_state(source)
        except ValueError:
            after, still_managed = "unreadable", False
    finally:
        if target_anchor is not None:
            target_anchor.close()
        cleanup_verified = _cleanup_execution_root(execution_root)
    unchanged = still_managed and after == before
    all_results = [*fact_probes.values(), *structure_probes.values(), *checks]
    facts_passed = not capture_cargo_facts or (
        set(fact_probes) == {"cargo-metadata"}
        and fact_probes["cargo-metadata"]["status"] == "passed"
    )
    structure_passed = not capture_cargo_structure or (
        set(structure_probes) == {"cargo-build"}
        and structure_probes["cargo-build"]["status"] == "passed"
        and bool(captured_products) and not product_capture_error
    )
    passed = (
        cleanup_verified and unchanged and facts_passed and structure_passed
        and len(checks) == 2
        and all(item["status"] == "passed" for item in checks)
    )
    blocked = (
        not cleanup_verified or not unchanged or product_capture_error
        or any(item["status"] == "blocked" for item in all_results)
    )
    diagnostics = [
        diagnostic
        for check in all_results if check["status"] == "blocked"
        for diagnostic in check.get("diagnostics", [])
    ]
    if not unchanged:
        diagnostics.append({
            "code": "managed_project_state_drift",
            "stage": "cargo-sandbox",
            "message": "Managed generation changed during sandboxed verification",
        })
    if not cleanup_verified:
        diagnostics.append({
            "code": "sandbox_cleanup_failed",
            "stage": "cargo-sandbox",
            "message": "Sandbox execution root could not be proven removed",
        })
    if product_capture_error:
        diagnostics.append({
            "code": "cargo_build_product_capture_invalid",
            "stage": "cargo-build-products",
            "message": "Cargo build products could not be captured safely",
        })
    result = {
        "schema_version": 1,
        "status": "passed" if passed else "blocked" if blocked else "failed",
        "cargo_executed": any(item["cargo_executed"] for item in all_results),
        "project_input_sha256": before,
        "project_state_before": before,
        "project_state_after": after,
        "project_state_unchanged": unchanged,
        "checks": checks,
        "sandbox": _sandbox_evidence(
            backend.contract, "executed", cleanup_verified=cleanup_verified,
            probe_receipt=probe_receipt,
        ),
        "environment_policy": _environment_policy(),
        "diagnostics": diagnostics,
        "semantic_gate": False,
        "proof_boundary": "Sandboxed Cargo topology/compile/test facts only; oracle and final verification remain separate" if capture_cargo_facts else "Sandboxed Cargo compile/test facts only; oracle and final verification remain separate",
    }
    if capture_cargo_facts:
        result["fact_probes"] = fact_probes
    if capture_cargo_structure:
        result["structure_probes"] = structure_probes
        result["_captured_rust_products"] = captured_products
        result["_captured_rustc_dep_info"] = captured_dep_info
    return result


__all__ = [
    "managed_project_input_sha256",
    "run_cargo_generation_gates",
    "run_cargo_project_gates",
]
