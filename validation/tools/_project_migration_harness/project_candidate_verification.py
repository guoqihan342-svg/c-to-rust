from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from .gate_evidence import write_content_addressed_json
from .ledger_security import LedgerError
from .project_candidate_domain import (
    candidate_verification_context,
    validate_candidate_project_domain,
)
from .project_candidate_verification_evidence import (
    bind_candidate_cargo_evidence,
    candidate_claim_boundary,
    candidate_verification_status,
    settle_candidate_native_links,
)
from .project_candidate_verification_receipt import (
    validate_candidate_project_verification,
)
from .project_completion_build_ir import (
    build_ir_allows_candidate_execution,
    build_ir_blocker_kinds,
    verify_project_final_build_ir,
)
from .project_verification import run_cargo_generation_gates
from .quarantine_generation import (
    materialize_rust_project_ir_quarantine_generation,
)
from .rust_project_ir_validation import reopen_rust_project_ir_bindings


def verify_candidate_project(
    *,
    run_id: str,
    migration_contract: Mapping[str, Any],
    rust_project_ir: Mapping[str, Any],
    candidate_descriptors: Sequence[Mapping[str, Any]],
    candidate_set_sha256: str,
    candidate_set_manifest: Mapping[str, Any],
    migration_manifest: Mapping[str, Any],
    repo_root: Path | None,
    artifact_root: Path,
    quarantine_root: Path,
    runtime_root: Path,
    ledger_path: Path,
    out_root: Path,
    out_root_rel: str,
    timeout_seconds: int = 300,
    symbol_candidate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run candidate-only whole-project Cargo evidence in a detached generation."""
    execution: Mapping[str, Any] | None = None
    try:
        root = Path(artifact_root).resolve(strict=True)
        binding = reopen_rust_project_ir_bindings(rust_project_ir, root)
    except (OSError, TypeError, ValueError) as error:
        return _blocked(
            "candidate_rust_project_ir_invalid", detail=type(error).__name__,
        )
    try:
        domain = validate_candidate_project_domain(
            run_id=run_id,
            migration_contract=migration_contract,
            rust_project_ir=rust_project_ir,
            rust_project_binding_sha256=binding["bindings_sha256"],
            candidate_set_sha256=candidate_set_sha256,
            candidate_set_manifest=candidate_set_manifest,
            artifact_root=root,
        )
    except (KeyError, OSError, TypeError, ValueError):
        return _blocked("candidate_project_domain_invalid")
    build_ir = verify_project_final_build_ir(
        migration_manifest=migration_manifest,
        repo_root=repo_root,
        artifact_root=root,
    )
    if not build_ir_allows_candidate_execution(build_ir):
        return _blocked(
            "candidate_build_ir_blocked",
            blockers=build_ir_blocker_kinds(build_ir),
            build_ir_verification=build_ir,
        )
    native_required = bool(rust_project_ir["native_link_requirements"])
    if build_ir.get("status") != "verified" and not native_required:
        return _blocked(
            "candidate_native_requirements_missing",
            build_ir_verification=build_ir,
        )
    materialized = materialize_rust_project_ir_quarantine_generation(
        rust_project_ir,
        candidate_descriptors,
        root,
        quarantine_root,
        candidate_set_sha256,
        candidate_set_manifest,
    )
    if materialized.get("status") != "materialized":
        return _blocked(
            "candidate_quarantine_materialization_failed",
            build_ir_verification=build_ir,
            materialization=materialized,
        )
    generation = _generation_path(quarantine_root, materialized)
    if generation is None:
        return _blocked(
            "candidate_quarantine_generation_invalid",
            build_ir_verification=build_ir,
            materialization=materialized,
        )
    try:
        execution = run_cargo_generation_gates(
            generation,
            runtime_root=runtime_root,
            timeout_seconds=timeout_seconds,
            capture_raw_output=True,
            capture_native_link_trace=native_required,
        )
        execution, checks, observations, cargo_statuses = (
            bind_candidate_cargo_evidence(
                execution,
                native_required=native_required,
                out_root=out_root,
                out_root_rel=out_root_rel,
            )
        )
    except (KeyError, OSError, TypeError, ValueError, LedgerError):
        return _blocked(
            "candidate_cargo_evidence_invalid",
            cargo_executed=_cargo_executed(execution),
            build_ir_verification=build_ir,
            materialization=materialized,
        )
    native = settle_candidate_native_links(
        rust_project_ir=rust_project_ir,
        migration_manifest=migration_manifest,
        artifact_root=root,
        ledger_path=ledger_path,
        out_root=out_root,
        execution=execution,
        checks=checks,
        observations=observations,
        symbol_candidate=symbol_candidate,
        cargo_passed=all(value == "passed" for value in cargo_statuses.values()),
    )
    status = candidate_verification_status(
        execution, observations, cargo_statuses, native, native_required,
    )
    payload = {
        "schema_version": 1,
        "artifact_kind": "candidate-project-verification",
        "status": status,
        **domain,
        "build_ir_verification": build_ir,
        "materialization": materialized,
        "execution": execution,
        "cargo_observations": observations,
        "cargo_statuses": cargo_statuses,
        "native_link_settlement": native,
        "state_effects": {
            "final_current_updated": False,
            "project_gate_records_written": 0,
            "candidate_only": True,
        },
        "claim_boundary": candidate_claim_boundary(
            status == "candidate-verified"
        ),
    }
    payload["verification_context_sha256"] = candidate_verification_context(
        domain, build_ir, materialized, execution, observations, native,
    )
    try:
        payload = validate_candidate_project_verification(payload)
    except (TypeError, ValueError, LedgerError):
        return _blocked(
            "candidate_verification_receipt_invalid",
            cargo_executed=_cargo_executed(execution),
            build_ir_verification=build_ir,
            materialization=materialized,
        )
    try:
        receipt = write_content_addressed_json(
            out_root, "candidate-project-verification", payload,
        )
    except (OSError, TypeError, ValueError, LedgerError):
        return _blocked(
            "candidate_verification_receipt_unavailable",
            cargo_executed=_cargo_executed(execution),
            build_ir_verification=build_ir,
            materialization=materialized,
        )
    return {
        **payload,
        "receipt": {
            **receipt,
            "path": f"{out_root_rel}/{receipt['path']}",
        },
    }


def _generation_path(
    quarantine_root: Path, materialized: Mapping[str, Any],
) -> Path | None:
    generation = materialized.get("generation")
    relative = generation.get("path") if isinstance(generation, Mapping) else None
    if not isinstance(relative, str) or not relative:
        return None
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        return None
    try:
        root = Path(quarantine_root).resolve(strict=True)
        target = root.joinpath(*path.parts).resolve(strict=True)
        target.relative_to(root)
    except (OSError, ValueError):
        return None
    return target


def _blocked(
    reason_code: str, *, cargo_executed: bool = False, **details: Any,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_kind": "candidate-project-verification",
        "status": "blocked",
        "reason_code": reason_code,
        "cargo_executed": cargo_executed,
        "state_effects": {
            "final_current_updated": False,
            "project_gate_records_written": 0,
            "candidate_only": True,
        },
        "claim_boundary": candidate_claim_boundary(False),
        **details,
    }


def _cargo_executed(value: Mapping[str, Any] | None) -> bool:
    return isinstance(value, Mapping) and value.get("cargo_executed") is True


__all__ = ["verify_candidate_project"]
