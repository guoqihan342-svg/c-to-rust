from __future__ import annotations

from pathlib import Path
from typing import Any

from .candidate_compile_verifier import verify_candidate_compile
from .candidate_final_verifier import verify_candidate_final
from .controller_gates import promote_current_verified_candidate
from .gate_candidate_sets import candidate_set_manifest
from .ledger import LedgerError, ProjectLedger
from .project_completion_semantics import SEMANTIC_RUNNERS, semantic_runner


def advance_gate_pending_candidates(
    *, ledger: ProjectLedger, run_id: str, out_root: Path,
    out_root_rel: str, quarantine_root: Path, runtime_root: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    advanced: list[dict[str, str]] = []
    for _step in range(10_000):
        states = ledger.unit_states(run_id)
        candidate_ready = sorted(
            str(item["unit_id"]) for item in states
            if item.get("status") == "candidate-ready"
        )
        if candidate_ready:
            return _result(
                "waiting", "candidate-worker-required", advanced,
                candidate_ready,
            )
        gate_pending = sorted(
            str(item["unit_id"]) for item in states
            if item.get("status") == "gate-pending"
        )
        if not gate_pending:
            return _result(
                "advanced" if advanced else "idle",
                "candidate-wave-advanced" if advanced else "candidate-wave-idle",
                advanced, [],
            )
        try:
            candidate_set = ledger.bind_verification_candidate_set(
                run_id=run_id, scope="wave-provisional",
            )
            with ledger.connect() as connection:
                manifest = candidate_set_manifest(
                    connection, run_id, candidate_set,
                )
            roots = manifest["roots"]
            root = next((item for item in roots if item in gate_pending), None)
            members = {
                str(item["unit_id"]): item for item in manifest["members"]
            }
            if root is None or root not in members:
                raise LedgerError("gate-pending candidate is outside its wave cohort")
            member = members[root]
            compile_result = verify_candidate_compile(
                ledger=ledger, run_id=run_id, unit_id=root,
                candidate_artifact_id=str(member["artifact_id"]),
                candidate_root=out_root, candidate_root_rel=out_root_rel,
                quarantine_root=quarantine_root, runtime_root=runtime_root,
                out_root=out_root, out_root_rel=out_root_rel,
                timeout_seconds=timeout_seconds,
                verification_scope="wave-provisional",
            )
            if compile_result.get("status") != "passed":
                return _gate_result(
                    compile_result, "candidate-wave-compile", advanced, [root],
                )
            for family in SEMANTIC_RUNNERS:
                semantic = semantic_runner(family)(
                    ledger=ledger, out_root=out_root,
                    out_root_rel=out_root_rel, run_id=run_id,
                    unit_id=root,
                    candidate_artifact_id=str(member["artifact_id"]),
                    verification_scope="wave-provisional",
                )
                if semantic.get("status") != "passed":
                    return _gate_result(
                        semantic, f"candidate-wave-{family}", advanced, [root],
                    )
            final = verify_candidate_final(
                ledger=ledger, out_root=out_root,
                out_root_rel=out_root_rel, run_id=run_id,
                unit_id=root,
                candidate_artifact_id=str(member["artifact_id"]),
                verification_scope="wave-provisional",
            )
            if final.get("status") != "passed":
                return _gate_result(
                    final, "candidate-wave-final", advanced, [root],
                )
            promoted = promote_current_verified_candidate(
                ledger=ledger, run_id=run_id, unit_id=root,
                candidate_artifact_id=str(member["artifact_id"]),
            )
            advanced.append({
                "unit_id": root,
                "candidate_artifact_id": str(member["artifact_id"]),
                "status": str(promoted["status"]),
            })
        except (KeyError, LedgerError, OSError, TypeError, ValueError) as error:
            return {
                **_result("blocked", "candidate-wave-verification", advanced, gate_pending),
                "blockers": [str(error)[:160]],
            }
    return {
        **_result("blocked", "candidate-wave-limit", advanced, []),
        "blockers": ["candidate wave advancement exceeded the unit bound"],
    }


def _gate_result(
    value: dict[str, Any], stage: str, advanced: list[dict[str, str]],
    unit_ids: list[str],
) -> dict[str, Any]:
    status = str(value.get("status", "blocked"))
    return {
        **_result(
            "repair-required" if status == "failed" else status,
            stage, advanced, unit_ids,
        ),
        "gate_result": value,
    }


def _result(
    status: str, stage: str, advanced: list[dict[str, str]],
    unit_ids: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_kind": "candidate-wave-completion",
        "status": status, "stage": stage,
        "advanced": list(advanced), "unit_ids": unit_ids,
        "blockers": [], "semantic_gate": False,
    }


__all__ = ["advance_gate_pending_candidates"]
