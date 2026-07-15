from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .build_ir import is_sha256
from .clang_fact_commands import validate_clang_fact_plan
from .clang_fact_runner_derived import validate_clang_derived_reference
from .clang_fact_runner_process import ClangProcessResult
from .clang_raw_output_evidence import validate_clang_raw_output_references
from .sandbox_contract import SandboxContract
from .sandbox_environment import canonical_environment_items, cargo_guest_environment
from .sandbox_probe import SandboxProbeReceipt


CLANG_FACT_RUN_RECEIPT_KIND = "clang-fact-run-receipt"
CLANG_FACT_TIMEOUT_SECONDS = 60
_RECEIPT_FIELDS = {
    "schema_version", "artifact_kind", "status", "reason_code", "gate",
    "unit_id", "plan", "toolchain", "target", "sandbox", "execution",
    "raw_outputs", "derived_evidence", "derivation", "section_closure", "semantic_gate",
    "translation_coverage_numerator", "receipt_sha256",
}
_EXECUTION_FIELDS = {
    "command_started", "returncode", "timed_out", "output_limit_exceeded",
    "cleanup_verified", "shell", "launcher_argv_sha256",
}
_BLOCK_REASONS = {
    "clang_process_not_started", "clang_execution_timeout",
    "clang_output_limit_exceeded", "clang_nonzero_exit",
    "clang_runtime_cleanup_failed", "clang_toolchain_drifted",
    "clang_fact_parse_failed", "clang_fact_evidence_blocked",
    "clang_derived_evidence_persist_failed",
}
_EXECUTION_REASONS = {
    "clang_process_not_started", "clang_execution_timeout",
    "clang_output_limit_exceeded", "clang_nonzero_exit",
    "clang_runtime_cleanup_failed",
}


def build_clang_fact_run_receipt(
    *, plan: Mapping[str, Any], build_ir: Mapping[str, Any],
    toolchain_receipt: Mapping[str, Any], sandbox_contract: SandboxContract,
    sandbox_probe: SandboxProbeReceipt, result: ClangProcessResult,
    cleanup_verified: bool, raw_outputs: Mapping[str, Any] | None,
    derived_evidence: Mapping[str, Any] | None, reason_code: str | None,
    ast_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    environment = canonical_environment_items(cargo_guest_environment())
    core = {
        "schema_version": 1,
        "artifact_kind": CLANG_FACT_RUN_RECEIPT_KIND,
        "status": "facts-ready" if reason_code is None else "blocked",
        "reason_code": reason_code,
        "gate": plan["gate"],
        "unit_id": plan["unit_id"],
        "plan": _plan_binding(plan),
        "toolchain": _toolchain_binding(toolchain_receipt),
        "target": _target_binding(plan),
        "sandbox": _sandbox_binding(
            plan, sandbox_contract, sandbox_probe, environment,
        ),
        "execution": {
            "command_started": result.started,
            "returncode": result.returncode,
            "timed_out": result.timed_out,
            "output_limit_exceeded": result.output_limit_exceeded,
            "cleanup_verified": cleanup_verified,
            "shell": False,
            "launcher_argv_sha256": result.launcher_argv_sha256,
        },
        "raw_outputs": dict(raw_outputs) if raw_outputs is not None else None,
        "derived_evidence": (
            dict(derived_evidence) if derived_evidence is not None else None
        ),
        "derivation": _derivation_binding(plan, ast_receipt),
        "section_closure": False,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    return validate_clang_fact_run_receipt(
        {**core, "receipt_sha256": content_sha256(core)}, plan=plan,
        build_ir=build_ir, toolchain_receipt=toolchain_receipt,
        sandbox_contract=sandbox_contract, sandbox_probe=sandbox_probe,
        ast_receipt=ast_receipt,
    )


def validate_clang_fact_run_receipt(
    value: Any, *, plan: Mapping[str, Any], build_ir: Mapping[str, Any],
    toolchain_receipt: Mapping[str, Any], sandbox_contract: SandboxContract,
    sandbox_probe: SandboxProbeReceipt,
    ast_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _RECEIPT_FIELDS:
        raise ValueError("clang_fact_run_receipt_fields_invalid")
    receipt = dict(value)
    fixed_plan = validate_clang_fact_plan(
        plan, build_ir, toolchain_receipt.get("portable_binding"),
    )
    environment = canonical_environment_items(cargo_guest_environment())
    core = {key: receipt[key] for key in receipt if key != "receipt_sha256"}
    if (
        receipt.get("schema_version") != 1
        or receipt.get("artifact_kind") != CLANG_FACT_RUN_RECEIPT_KIND
        or receipt.get("receipt_sha256") != content_sha256(core)
        or receipt.get("gate") != fixed_plan["gate"]
        or receipt.get("unit_id") != fixed_plan["unit_id"]
        or receipt.get("plan") != _plan_binding(fixed_plan)
        or receipt.get("toolchain") != _toolchain_binding(toolchain_receipt)
        or receipt.get("target") != _target_binding(fixed_plan)
        or receipt.get("sandbox") != _sandbox_binding(
            fixed_plan, sandbox_contract, sandbox_probe, environment,
        )
        or receipt.get("derivation") != _derivation_binding(fixed_plan, ast_receipt)
        or receipt.get("section_closure") is not False
        or receipt.get("semantic_gate") is not False
        or receipt.get("translation_coverage_numerator") != 0
    ):
        raise ValueError("clang_fact_run_receipt_invalid")
    _validate_execution_and_raw(receipt, fixed_plan)
    return receipt


def guest_command(plan: Mapping[str, Any]) -> tuple[str, ...]:
    argv = plan.get("argv")
    if not isinstance(argv, list) or not argv or argv[0] != "clang":
        raise ValueError("clang_fact_runner_fixed_command_required")
    return ("/toolchain/bin/clang", *argv[1:])


def _plan_binding(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {key: plan[key] for key in (
        "plan_sha256", "argv_sha256", "input_sha256", "build_ir_sha256",
        "build_ir_semantic_sha256", "compile_context_sha256",
    )}


def _toolchain_binding(receipt: Mapping[str, Any]) -> dict[str, Any]:
    portable = receipt["portable_binding"]
    return {
        "receipt_sha256": receipt["receipt_sha256"],
        "portable_binding_sha256": portable["binding_sha256"],
        "host_evidence": dict(receipt["host_evidence"]),
        "version_probe_sha256": portable["version"]["stdout_sha256"],
        "target_probe_sha256": portable["target"]["stdout_sha256"],
        "proof_boundary": {
            "system_include_closure": False,
            "system_include_source": "host-read-only-unbound",
            "resource_dir_bound": True,
            "sysroot_path_probe_bound": portable["sysroot"]["status"] == "reported",
        },
    }


def _target_binding(plan: Mapping[str, Any]) -> dict[str, Any]:
    target = plan["target_context"]
    return {
        "target_context_sha256": plan["target_context_sha256"],
        "build_ir_host_target": target["build_ir_host_target"],
        "clang_target": target["clang_target"],
    }


def _derivation_binding(
    plan: Mapping[str, Any], ast_receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if plan.get("gate") == "clang-ast":
        if ast_receipt is not None:
            raise ValueError("clang_fact_run_ast_dependency_forbidden")
        return {
            "kind": "raw-ast-to-interface-facts",
            "ast_receipt_sha256": None,
            "ast_derived_evidence": None,
        }
    if not isinstance(ast_receipt, Mapping):
        raise ValueError("clang_fact_run_ast_dependency_required")
    reference = ast_receipt.get("derived_evidence")
    ast_plan = ast_receipt.get("plan")
    if not isinstance(ast_plan, Mapping):
        raise ValueError("clang_fact_run_ast_dependency_invalid")
    bound = validate_clang_derived_reference(
        reference, plan_sha256=str(ast_plan.get("plan_sha256")),
    )
    return {
        "kind": "ast-selected-record-layout",
        "ast_receipt_sha256": ast_receipt.get("receipt_sha256"),
        "ast_derived_evidence": bound,
    }


def _sandbox_binding(
    plan: Mapping[str, Any], contract: SandboxContract,
    probe: SandboxProbeReceipt, environment: tuple[tuple[str, str], ...],
) -> dict[str, Any]:
    execution_plan = {
        "plan_sha256": plan["plan_sha256"],
        "guest_argv_sha256": content_sha256(guest_command(plan)),
        "timeout_seconds": CLANG_FACT_TIMEOUT_SECONDS,
        "requirements_sha256": contract.requirements.sha256,
        "environment_sha256": content_sha256(environment),
    }
    return {
        "contract_sha256": contract.sha256,
        "probe_receipt_sha256": probe.sha256,
        "probe_plan_sha256": probe.probe_plan_sha256,
        "probe_raw_observation_sha256": probe.raw_observation_sha256,
        "execution_plan_sha256": content_sha256(execution_plan),
    }


def _validate_execution_and_raw(
    receipt: Mapping[str, Any], plan: Mapping[str, Any],
) -> None:
    execution = receipt.get("execution")
    if not isinstance(execution, Mapping) or set(execution) != _EXECUTION_FIELDS:
        raise ValueError("clang_fact_run_execution_invalid")
    started = execution.get("command_started")
    if (
        type(started) is not bool or type(execution.get("timed_out")) is not bool
        or type(execution.get("output_limit_exceeded")) is not bool
        or type(execution.get("cleanup_verified")) is not bool
        or execution.get("shell") is not False
        or not is_sha256(execution.get("launcher_argv_sha256"))
        or (
            execution.get("returncode") is not None
            and type(execution.get("returncode")) is not int
        )
    ):
        raise ValueError("clang_fact_run_execution_invalid")
    raw = receipt.get("raw_outputs")
    if started:
        validate_clang_raw_output_references(
            raw, gate_kind=plan["gate"], plan_sha256=plan["plan_sha256"],
            unit_id=plan["unit_id"],
        )
    elif raw is not None:
        raise ValueError("clang_fact_run_unstarted_raw_output_invalid")
    derived = receipt.get("derived_evidence")
    if derived is not None:
        validate_clang_derived_reference(
            derived, plan_sha256=str(plan["plan_sha256"]),
        )
    ready = receipt.get("status") == "facts-ready"
    execution_reason = _execution_reason(execution)
    reason = receipt.get("reason_code")
    if (
        (execution_reason is not None and reason != execution_reason)
        or (execution_reason is None and reason in _EXECUTION_REASONS)
    ):
        raise ValueError("clang_fact_run_reason_code_drifted")
    if ready != (reason is None):
        raise ValueError("clang_fact_run_status_invalid")
    if ready:
        if not (
            started and execution.get("returncode") == 0
            and not execution.get("timed_out")
            and not execution.get("output_limit_exceeded")
            and execution.get("cleanup_verified") is True
            and isinstance(derived, Mapping)
        ):
            raise ValueError("clang_fact_run_ready_state_invalid")
    elif receipt.get("status") != "blocked" or reason not in _BLOCK_REASONS:
        raise ValueError("clang_fact_run_blocked_state_invalid")
    if receipt.get("reason_code") == "clang_fact_evidence_blocked" and derived is None:
        raise ValueError("clang_fact_run_blocked_evidence_missing")
    if receipt.get("reason_code") not in {
        None, "clang_fact_evidence_blocked",
    } and derived is not None:
        raise ValueError("clang_fact_run_untrusted_derived_evidence")


def _execution_reason(execution: Mapping[str, Any]) -> str | None:
    checks = (
        (not execution.get("command_started"), "clang_process_not_started"),
        (execution.get("timed_out") is True, "clang_execution_timeout"),
        (execution.get("output_limit_exceeded") is True,
         "clang_output_limit_exceeded"),
        (execution.get("returncode") != 0, "clang_nonzero_exit"),
        (execution.get("cleanup_verified") is not True,
         "clang_runtime_cleanup_failed"),
    )
    return next((reason for failed, reason in checks if failed), None)


__all__ = [
    "CLANG_FACT_RUN_RECEIPT_KIND", "CLANG_FACT_TIMEOUT_SECONDS",
    "build_clang_fact_run_receipt", "guest_command",
    "validate_clang_fact_run_receipt",
]
