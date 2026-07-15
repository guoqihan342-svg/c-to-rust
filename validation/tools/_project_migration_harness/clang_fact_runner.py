from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .clang_fact_commands import validate_clang_fact_plan
from .clang_fact_runner_derived import write_clang_derived_evidence
from .clang_fact_runner_facts import (
    clang_fact_evidence_ready, derive_clang_fact_evidence,
)
from .clang_fact_runner_paths import (
    cleanup_runtime, create_runtime, fixed_out_root, load_clang_host_bindings,
    validate_c_repository, validate_clang_sandbox,
    verify_clang_host_binding_current,
)
from .clang_fact_runner_process import ClangProcessResult, run_bounded_bubblewrap
from .clang_fact_runner_receipt import (
    CLANG_FACT_RUN_RECEIPT_KIND, CLANG_FACT_TIMEOUT_SECONDS,
    build_clang_fact_run_receipt, guest_command,
    validate_clang_fact_run_receipt,
)
from .clang_fact_runner_reopen import (
    load_layout_ast_evidence, reopen_clang_fact_run_receipt,
)
from .clang_raw_output_evidence import write_clang_raw_outputs
from .ledger_security import LedgerError
from .sandbox_bubblewrap_argv import build_bubblewrap_argv, resource_limiter
from .sandbox_contract import SandboxContract
from .sandbox_environment import canonical_environment_items, cargo_guest_environment
from .sandbox_probe import SandboxProbeReceipt


def run_clang_fact_plan(
    *, ledger_path: Path, out_root_rel: str, c_repo_root: Path,
    runtime_parent: Path, bubblewrap_launcher: Path,
    sandbox_contract: SandboxContract, sandbox_probe: SandboxProbeReceipt,
    build_ir: Mapping[str, Any], toolchain_receipt: Mapping[str, Any],
    plan: Mapping[str, Any], ast_plan: Mapping[str, Any] | None = None,
    ast_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    host = load_clang_host_bindings(ledger_path, toolchain_receipt)
    fixed_plan = validate_clang_fact_plan(plan, build_ir, host.portable)
    repository, allowed_sources = validate_c_repository(c_repo_root, build_ir)
    interface = _interface_dependency(
        ledger_path, repository, fixed_plan, ast_plan, ast_receipt, build_ir,
        toolchain_receipt, sandbox_contract, sandbox_probe,
    )
    out_root = fixed_out_root(ledger_path)
    launcher = validate_clang_sandbox(
        bubblewrap_launcher, sandbox_contract, sandbox_probe, host.portable,
    )
    environment = canonical_environment_items(cargo_guest_environment())
    runtime = create_runtime(runtime_parent, repository)
    argv = build_bubblewrap_argv(
        launcher=launcher, workspace=repository, runtime=runtime,
        tool_bindings=host.tool_bindings, environment=environment,
        guest_command=guest_command(fixed_plan),
    )
    raw: dict[str, Any] | None = None
    try:
        result = run_bounded_bubblewrap(
            argv, timeout_seconds=CLANG_FACT_TIMEOUT_SECONDS,
            max_stdout_bytes=fixed_plan["max_stdout_bytes"],
            max_stderr_bytes=fixed_plan["max_stderr_bytes"],
            max_combined_bytes=fixed_plan["max_combined_bytes"],
            preexec_fn=resource_limiter(sandbox_contract),
        )
        result = _bounded_result(result, fixed_plan)
        if result.started:
            raw = write_clang_raw_outputs(
                out_root, out_root_rel, gate_kind=fixed_plan["gate"],
                plan_sha256=fixed_plan["plan_sha256"],
                unit_id=fixed_plan["unit_id"], stdout=result.stdout,
                stderr=result.stderr,
            )
    finally:
        cleanup_verified = cleanup_runtime(runtime)
    toolchain_drifted = _toolchain_drifted(
        result, ledger_path, toolchain_receipt,
    )
    facts, parse_failed = _derive_if_eligible(
        fixed_plan, result, cleanup_verified, toolchain_drifted,
        allowed_sources, interface,
    )
    derived, persist_failed = _persist_derived(out_root, fixed_plan, facts)
    reason = _reason(
        result, cleanup_verified, toolchain_drifted, parse_failed,
        persist_failed,
        facts is not None and not clang_fact_evidence_ready(fixed_plan["gate"], facts),
    )
    return build_clang_fact_run_receipt(
        plan=fixed_plan, build_ir=build_ir, toolchain_receipt=host.receipt,
        sandbox_contract=sandbox_contract, sandbox_probe=sandbox_probe,
        result=result, cleanup_verified=cleanup_verified, raw_outputs=raw,
        derived_evidence=derived, reason_code=reason, ast_receipt=ast_receipt,
    )


def _interface_dependency(
    ledger_path: Path, repository: Path, plan: Mapping[str, Any],
    ast_plan: Mapping[str, Any] | None, ast_receipt: Mapping[str, Any] | None,
    build_ir: Mapping[str, Any], toolchain_receipt: Mapping[str, Any],
    sandbox_contract: SandboxContract, sandbox_probe: SandboxProbeReceipt,
) -> dict[str, Any] | None:
    if plan.get("gate") == "clang-ast":
        if ast_plan is not None or ast_receipt is not None:
            raise ValueError("clang_fact_runner_ast_dependency_forbidden")
        return None
    return load_layout_ast_evidence(
        ledger_path, c_repo_root=repository, layout_plan=plan,
        ast_plan=ast_plan, ast_receipt=ast_receipt, build_ir=build_ir,
        toolchain_receipt=toolchain_receipt, sandbox_contract=sandbox_contract,
        sandbox_probe=sandbox_probe,
    )


def _derive_if_eligible(
    plan: Mapping[str, Any], result: ClangProcessResult, cleanup: bool,
    drifted: bool, sources: Mapping[str, str],
    interface: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, bool]:
    if not (
        result.started and result.returncode == 0 and not result.timed_out
        and not result.output_limit_exceeded and cleanup and not drifted
    ):
        return None, False
    try:
        return derive_clang_fact_evidence(
            plan, stdout=result.stdout, stderr=result.stderr,
            allowed_sources=sources, interface_evidence=interface,
        ), False
    except (TypeError, ValueError):
        return None, True


def _persist_derived(
    out_root: Path, plan: Mapping[str, Any], facts: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, bool]:
    if facts is None:
        return None, False
    try:
        return write_clang_derived_evidence(
            out_root, plan_sha256=plan["plan_sha256"], evidence=facts,
        ), False
    except (LedgerError, OSError, TypeError, ValueError):
        return None, True


def _toolchain_drifted(
    result: ClangProcessResult, ledger_path: Path,
    receipt: Mapping[str, Any],
) -> bool:
    if not result.started:
        return False
    try:
        verify_clang_host_binding_current(ledger_path, receipt)
    except (LedgerError, OSError, TypeError, ValueError):
        return True
    return False


def _reason(
    result: ClangProcessResult, cleanup: bool, drifted: bool,
    parse_failed: bool, persist_failed: bool, evidence_blocked: bool,
) -> str | None:
    checks = (
        (not result.started, "clang_process_not_started"),
        (result.timed_out, "clang_execution_timeout"),
        (result.output_limit_exceeded, "clang_output_limit_exceeded"),
        (result.returncode != 0, "clang_nonzero_exit"),
        (not cleanup, "clang_runtime_cleanup_failed"),
        (drifted, "clang_toolchain_drifted"),
        (parse_failed, "clang_fact_parse_failed"),
        (persist_failed, "clang_derived_evidence_persist_failed"),
        (evidence_blocked, "clang_fact_evidence_blocked"),
    )
    return next((reason for failed, reason in checks if failed), None)


def _bounded_result(
    result: ClangProcessResult, plan: Mapping[str, Any],
) -> ClangProcessResult:
    if not isinstance(result, ClangProcessResult):
        raise TypeError("clang_fact_runner_process_result_invalid")
    stdout = result.stdout[:plan["max_stdout_bytes"]]
    remaining = max(0, plan["max_combined_bytes"] - len(stdout))
    stderr = result.stderr[:min(plan["max_stderr_bytes"], remaining)]
    overflow = (
        len(stdout) != len(result.stdout) or len(stderr) != len(result.stderr)
        or len(result.stdout) + len(result.stderr) > plan["max_combined_bytes"]
    )
    return ClangProcessResult(
        result.started, result.returncode, stdout, stderr,
        timed_out=result.timed_out,
        output_limit_exceeded=result.output_limit_exceeded or overflow,
        launcher_argv_sha256=result.launcher_argv_sha256,
    )


__all__ = [
    "CLANG_FACT_RUN_RECEIPT_KIND", "CLANG_FACT_TIMEOUT_SECONDS",
    "reopen_clang_fact_run_receipt", "run_clang_fact_plan",
    "validate_clang_fact_run_receipt",
]
