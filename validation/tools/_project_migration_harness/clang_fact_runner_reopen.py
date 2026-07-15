from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .clang_fact_commands import validate_clang_fact_plan
from .clang_fact_runner_derived import read_clang_derived_evidence
from .clang_fact_runner_facts import (
    clang_fact_evidence_ready, derive_clang_fact_evidence,
)
from .clang_fact_runner_paths import (
    load_clang_host_bindings, validate_c_repository,
    verify_clang_host_binding_current,
)
from .clang_fact_runner_receipt import validate_clang_fact_run_receipt
from .clang_raw_output_evidence import read_clang_raw_outputs
from .ledger_security import LedgerError
from .sandbox_contract import SandboxContract
from .sandbox_probe import SandboxProbeReceipt


def reopen_clang_fact_run_receipt(
    ledger_path: Path, value: Mapping[str, Any], *, c_repo_root: Path,
    plan: Mapping[str, Any], build_ir: Mapping[str, Any],
    toolchain_receipt: Mapping[str, Any], sandbox_contract: SandboxContract,
    sandbox_probe: SandboxProbeReceipt,
    ast_plan: Mapping[str, Any] | None = None,
    ast_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    host = load_clang_host_bindings(ledger_path, toolchain_receipt)
    fixed_plan = validate_clang_fact_plan(plan, build_ir, host.portable)
    receipt = validate_clang_fact_run_receipt(
        value, plan=fixed_plan, build_ir=build_ir,
        toolchain_receipt=host.receipt, sandbox_contract=sandbox_contract,
        sandbox_probe=sandbox_probe, ast_receipt=ast_receipt,
    )
    _, sources = validate_c_repository(c_repo_root, build_ir)
    execution = receipt["execution"]
    if execution["command_started"]:
        streams = read_clang_raw_outputs(
            ledger_path, receipt["raw_outputs"], gate_kind=receipt["gate"],
            plan_sha256=receipt["plan"]["plan_sha256"], unit_id=receipt["unit_id"],
        )
        if _eligible(execution, receipt.get("reason_code")):
            interface = _interface_dependency(
                ledger_path, c_repo_root, fixed_plan, build_ir,
                toolchain_receipt, sandbox_contract, sandbox_probe,
                ast_plan, ast_receipt,
            )
            _verify_derivation(
                ledger_path, receipt, fixed_plan, streams, sources, interface,
            )
    verify_clang_host_binding_current(ledger_path, toolchain_receipt)
    return receipt


def load_layout_ast_evidence(
    ledger_path: Path, *, c_repo_root: Path, layout_plan: Mapping[str, Any],
    ast_plan: Mapping[str, Any] | None, ast_receipt: Mapping[str, Any] | None,
    build_ir: Mapping[str, Any], toolchain_receipt: Mapping[str, Any],
    sandbox_contract: SandboxContract, sandbox_probe: SandboxProbeReceipt,
) -> dict[str, Any]:
    value = _interface_dependency(
        ledger_path, c_repo_root, layout_plan, build_ir, toolchain_receipt,
        sandbox_contract, sandbox_probe, ast_plan, ast_receipt,
    )
    if value is None:
        raise ValueError("clang_fact_runner_layout_ast_dependency_required")
    return value


def _interface_dependency(
    ledger_path: Path, c_repo_root: Path, plan: Mapping[str, Any],
    build_ir: Mapping[str, Any], toolchain_receipt: Mapping[str, Any],
    sandbox_contract: SandboxContract, sandbox_probe: SandboxProbeReceipt,
    ast_plan: Mapping[str, Any] | None, ast_receipt: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if plan.get("gate") == "clang-ast":
        if ast_plan is not None or ast_receipt is not None:
            raise ValueError("clang_fact_runner_ast_dependency_forbidden")
        return None
    if not isinstance(ast_plan, Mapping) or not isinstance(ast_receipt, Mapping):
        raise ValueError("clang_fact_runner_layout_ast_dependency_required")
    if (
        ast_plan.get("gate") != "clang-ast"
        or ast_plan.get("unit_id") != plan.get("unit_id")
        or ast_plan.get("build_ir_sha256") != plan.get("build_ir_sha256")
        or ast_plan.get("build_ir_semantic_sha256")
        != plan.get("build_ir_semantic_sha256")
        or ast_plan.get("toolchain_portable_sha256")
        != plan.get("toolchain_portable_sha256")
        or ast_plan.get("target_context_sha256") != plan.get("target_context_sha256")
    ):
        raise ValueError("clang_fact_runner_layout_ast_dependency_drifted")
    reopened = reopen_clang_fact_run_receipt(
        ledger_path, ast_receipt, c_repo_root=c_repo_root, plan=ast_plan,
        build_ir=build_ir, toolchain_receipt=toolchain_receipt,
        sandbox_contract=sandbox_contract, sandbox_probe=sandbox_probe,
    )
    if reopened.get("status") != "facts-ready":
        raise ValueError("clang_fact_runner_layout_ast_facts_unavailable")
    return read_clang_derived_evidence(
        ledger_path, reopened["derived_evidence"],
        plan_sha256=ast_plan["plan_sha256"],
    )


def _verify_derivation(
    ledger_path: Path, receipt: Mapping[str, Any], plan: Mapping[str, Any],
    streams: Mapping[str, bytes], sources: Mapping[str, str],
    interface: Mapping[str, Any] | None,
) -> None:
    try:
        expected = derive_clang_fact_evidence(
            plan, stdout=streams["stdout"], stderr=streams["stderr"],
            allowed_sources=sources, interface_evidence=interface,
        )
    except (TypeError, ValueError) as error:
        if receipt.get("reason_code") == "clang_fact_parse_failed" \
                and receipt.get("derived_evidence") is None:
            return
        raise LedgerError("Clang fact evidence cannot be reparsed") from error
    ready = clang_fact_evidence_ready(str(plan["gate"]), expected)
    reason = receipt.get("reason_code")
    if reason == "clang_derived_evidence_persist_failed":
        if receipt.get("derived_evidence") is not None:
            raise LedgerError("Clang failed derivation unexpectedly has a reference")
        return
    if reason != (None if ready else "clang_fact_evidence_blocked"):
        raise LedgerError("Clang fact derivation status drifted")
    stored = read_clang_derived_evidence(
        ledger_path, receipt["derived_evidence"],
        plan_sha256=plan["plan_sha256"],
    )
    if stored != expected:
        raise LedgerError("Clang fact evidence reparse drifted")


def _eligible(execution: Mapping[str, Any], reason: Any) -> bool:
    return bool(
        execution.get("command_started")
        and execution.get("returncode") == 0
        and execution.get("timed_out") is False
        and execution.get("output_limit_exceeded") is False
        and execution.get("cleanup_verified") is True
        and reason in {
            None, "clang_fact_parse_failed",
            "clang_derived_evidence_persist_failed",
            "clang_fact_evidence_blocked",
        }
    )


__all__ = ["load_layout_ast_evidence", "reopen_clang_fact_run_receipt"]
