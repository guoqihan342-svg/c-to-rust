from __future__ import annotations

import hashlib
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .build_ir_validation import validate_build_ir
from .c_compilation_fact_raw import write_c_compilation_raw_outputs
from .c_compilation_fact_runtime import (
    CCompilationRuntime,
    prepare_c_compilation_runtime,
    run_c_syntax_plan,
)
from .c_compilation_fact_validation import (
    compiler_facts_for_index,
    validate_c_compilation_fact_bundle,
)


C_COMPILATION_FACT_BUNDLE_KIND = "c-compilation-fact-bundle-v1"
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_PROFILES = {"competition", "development"}


def collect_c_compilation_fact_bundle(
    *,
    repo_root: Path,
    out_root: Path,
    build_ir: Mapping[str, Any],
    profile: str,
) -> dict[str, Any]:
    validate_build_ir(build_ir)
    if profile not in _PROFILES:
        raise ValueError("c_compilation_fact_profile_invalid")
    units = sorted(
        build_ir["translation_units"], key=lambda item: str(item["unit_id"])
    )
    try:
        runtime = prepare_c_compilation_runtime(Path(repo_root), build_ir)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        return _bundle(
            profile=profile,
            build_ir=build_ir,
            runtime=None,
            receipts=[],
            total=len(units),
            unavailable_reason=_portable_reason(error),
        )
    receipts = [
        _run_unit(
            runtime=runtime,
            repo_root=Path(repo_root),
            out_root=Path(out_root),
            unit=unit,
        )
        for unit in units
    ]
    return _bundle(
        profile=profile,
        build_ir=build_ir,
        runtime=runtime,
        receipts=receipts,
        total=len(units),
        unavailable_reason=None,
    )


def _run_unit(
    *,
    runtime: CCompilationRuntime,
    repo_root: Path,
    out_root: Path,
    unit: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_parent = out_root / "runtime/c-compilation"
    try:
        plan, result, cleanup, compiler_stable = run_c_syntax_plan(
            runtime=runtime,
            repo_root=repo_root,
            runtime_parent=runtime_parent,
            unit=unit,
        )
        raw = write_c_compilation_raw_outputs(
            out_root,
            unit_id=str(unit["unit_id"]),
            plan_sha256=plan["plan_sha256"],
            stdout=result.stdout,
            stderr=result.stderr,
        )
        reason = _execution_reason(result, cleanup, compiler_stable)
        return _receipt(
            unit=unit,
            runtime=runtime,
            plan=plan,
            raw=raw,
            result=result,
            reason=reason,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        return _blocked_receipt(unit, runtime, _portable_reason(error))


def _receipt(
    *,
    unit: Mapping[str, Any],
    runtime: CCompilationRuntime,
    plan: Mapping[str, Any],
    raw: Mapping[str, Any],
    result: Any,
    reason: str | None,
) -> dict[str, Any]:
    core = {
        "schema_version": 1,
        "artifact_kind": "c-compilation-syntax-receipt",
        "unit_id": unit["unit_id"],
        "source_sha256": unit["source"]["sha256"],
        "expanded_argv_sha256": unit["compile_arguments"]["expanded_argv_sha256"],
        "toolchain_id": unit["toolchain_id"],
        "toolchain_binding_sha256": plan["toolchain_binding_sha256"],
        "compile_context_sha256": plan["compile_context_sha256"],
        "plan_sha256": plan["plan_sha256"],
        "sandbox_probe_sha256": runtime.probe.sha256,
        "status": "syntax_passed" if reason is None else "blocked",
        "reason_code": reason,
        "command_started": result.started,
        "returncode": result.returncode,
        "timed_out": result.timed_out,
        "output_limit_exceeded": result.output_limit_exceeded,
        "diagnostics_sha256": raw["stderr_sha256"],
        "diagnostic_bytes": raw["stderr_ref"]["size_bytes"],
        "raw_outputs": dict(raw),
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    return {**core, "receipt_sha256": content_sha256(core)}


def _blocked_receipt(
    unit: Mapping[str, Any],
    runtime: CCompilationRuntime,
    reason: str,
) -> dict[str, Any]:
    binding = runtime.compilers[str(unit["toolchain_id"])]
    plan_core = {
        "unit_id": unit["unit_id"],
        "source_sha256": unit["source"]["sha256"],
        "expanded_argv_sha256": unit["compile_arguments"]["expanded_argv_sha256"],
        "toolchain_binding_sha256": binding.portable["binding_sha256"],
        "reason_code": reason,
    }
    core = {
        "schema_version": 1,
        "artifact_kind": "c-compilation-syntax-receipt",
        "unit_id": unit["unit_id"],
        "source_sha256": unit["source"]["sha256"],
        "expanded_argv_sha256": unit["compile_arguments"]["expanded_argv_sha256"],
        "toolchain_id": unit["toolchain_id"],
        "toolchain_binding_sha256": binding.portable["binding_sha256"],
        "compile_context_sha256": content_sha256(plan_core),
        "plan_sha256": content_sha256({**plan_core, "kind": "blocked-plan"}),
        "sandbox_probe_sha256": runtime.probe.sha256,
        "status": "blocked",
        "reason_code": reason,
        "command_started": False,
        "returncode": None,
        "timed_out": False,
        "output_limit_exceeded": False,
        "diagnostics_sha256": _EMPTY_SHA256,
        "diagnostic_bytes": 0,
        "raw_outputs": None,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    return {**core, "receipt_sha256": content_sha256(core)}


def _bundle(
    *,
    profile: str,
    build_ir: Mapping[str, Any],
    runtime: CCompilationRuntime | None,
    receipts: list[dict[str, Any]],
    total: int,
    unavailable_reason: str | None,
) -> dict[str, Any]:
    passed = sum(item["status"] == "syntax_passed" for item in receipts)
    blocked = len(receipts) - passed
    status = (
        "unavailable" if not receipts
        else "ready" if passed == total and blocked == 0
        else "ready_with_boundaries"
    )
    sandbox = None if runtime is None else {
        "contract": runtime.contract.payload(),
        "contract_sha256": runtime.contract.sha256,
        "probe": runtime.probe.payload(),
        "probe_sha256": runtime.probe.sha256,
    }
    toolchains = [] if runtime is None else [
        runtime.compilers[key].portable for key in sorted(runtime.compilers)
    ]
    core = {
        "schema_version": 1,
        "artifact_kind": C_COMPILATION_FACT_BUNDLE_KIND,
        "status": status,
        "profile": profile,
        "build_ir_semantic_sha256": build_ir["semantic_sha256"],
        "sandbox": sandbox,
        "toolchains": toolchains,
        "units": receipts,
        "summary": {
            "total": total,
            "observed": len(receipts),
            "passed": passed,
            "blocked": blocked,
            "unavailable_reason": unavailable_reason,
        },
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "scope": "compiler_syntax_witness_only",
        },
    }
    result = {**core, "bundle_sha256": content_sha256(core)}
    validate_c_compilation_fact_bundle(result)
    return result


def _execution_reason(result: Any, cleanup: bool, stable: bool) -> str | None:
    checks = (
        (not result.started, "compiler_process_not_started"),
        (result.timed_out, "compiler_execution_timeout"),
        (result.output_limit_exceeded, "compiler_output_limit_exceeded"),
        (result.returncode != 0, "compiler_nonzero_exit"),
        (not cleanup, "compiler_runtime_cleanup_failed"),
        (not stable, "compiler_toolchain_drifted"),
    )
    return next((reason for failed, reason in checks if failed), None)


def _portable_reason(error: BaseException) -> str:
    text = str(error).strip()
    if text and all(character.isalnum() or character in "_.-" for character in text):
        return text[:160]
    return f"{type(error).__name__.lower()}_during_c_compilation_fact_stage"


__all__ = [
    "C_COMPILATION_FACT_BUNDLE_KIND",
    "collect_c_compilation_fact_bundle",
    "compiler_facts_for_index",
    "validate_c_compilation_fact_bundle",
]
