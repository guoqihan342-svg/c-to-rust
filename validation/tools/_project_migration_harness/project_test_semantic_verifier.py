from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .artifacts import write_json_artifact
from .gate_evidence import write_content_addressed_json
from .ledger import LedgerError, ProjectLedger
from .project_generation_context import load_managed_project_context
from .project_host_gates import record_host_project_observation
from .project_test_inventory_validation import (
    manifest_project_test_inventory_reference,
    reopen_manifest_project_test_inventory,
)
from .project_test_completeness import derive_project_test_completeness
from .project_test_mapping import derive_project_test_mapping
from .project_test_semantic_evidence import (
    bound_project_test_gate_observation,
    reopen_project_test_semantic_evidence,
)
from .project_test_semantic_repair import register_project_test_candidate_repairs


_ORACLE_SCOPE = "project-test/oracle"


def verify_project_test_semantics(
    *, ledger: ProjectLedger, run_id: str, repo_root: Path | None,
    artifact_root: Path, out_root_rel: str, project_root: Path,
    runtime_root: Path, migration_manifest: Mapping[str, Any],
    candidate_members: Sequence[Mapping[str, Any]], timeout_seconds: int = 300,
) -> dict[str, Any]:
    if repo_root is None:
        return _blocked("project_test_repo_root_missing")
    try:
        context = load_managed_project_context(project_root, candidate_members)
        rust_project_ir = context["rust_project_ir"]
        inventory = reopen_manifest_project_test_inventory(
            repo_root=repo_root, artifact_root=artifact_root,
            migration_manifest=migration_manifest,
        )
        inventory_ref = manifest_project_test_inventory_reference(migration_manifest)
        inventory_receipt = write_json_artifact(
            artifact_root, "completion/project-test-inventory-reopened.json",
            {
                "schema_version": 1, "status": "reopened",
                "inventory_sha256": inventory["inventory_sha256"],
                "test_count": len(inventory["tests"]), "semantic_gate": False,
            },
        )
        mapping = derive_project_test_mapping(inventory, rust_project_ir)
        mapping_ref = write_json_artifact(
            artifact_root, "completion/project-test-mapping.json", mapping,
        )
        if mapping.get("status") != "ready":
            return _blocked(
                _first_blocker(mapping, "project_test_mapping_blocked"),
                inventory_receipt=inventory_receipt, mapping=mapping_ref,
            )
        completeness = derive_project_test_completeness(
            inventory, mapping, rust_project_ir,
        )
        completeness_ref = write_json_artifact(
            artifact_root, "completion/project-test-completeness.json",
            completeness,
        )
        if completeness.get("status") != "ready":
            return _blocked(
                _first_blocker(
                    completeness, "project_test_completeness_blocked",
                ),
                inventory_receipt=inventory_receipt, mapping=mapping_ref,
                completeness=completeness_ref,
            )
        oracle = _run_project_test_oracle(
            repo_root=repo_root, generation_root=context["generation_root"],
            runtime_root=runtime_root, rust_project_ir=rust_project_ir,
            inventory=inventory, mapping=mapping, completeness=completeness,
            excludes=(artifact_root, project_root, runtime_root),
            timeout_seconds=timeout_seconds,
        )
        oracle_ref = write_content_addressed_json(
            artifact_root, _ORACLE_SCOPE, oracle,
        )
        observation = oracle.get("observation")
        if not isinstance(observation, Mapping):
            return _blocked(
                str(oracle.get("reason_code") or "project_test_oracle_blocked"),
                inventory_receipt=inventory_receipt, mapping=mapping_ref,
                completeness=completeness_ref,
                oracle=oracle_ref,
            )
        gate_observation = bound_project_test_gate_observation(
            observation, oracle_ref,
        )
        candidate_set = ledger.bind_current_candidate_set(run_id=run_id)
        record = record_host_project_observation(
            ledger=ledger, out_root=artifact_root, out_root_rel=out_root_rel,
            run_id=run_id, gate_kind="oracle-replay",
            candidate_set_sha256=candidate_set, observation=gate_observation,
            diagnostic_codes=(
                [] if oracle.get("status") == "passed"
                else ["project-test-logic-mismatch"]
            ),
        )
        passed = oracle.get("status") == "passed" and record["gate_status"] == "passed"
        repair = None
        if not passed:
            repair = register_project_test_candidate_repairs(
                ledger=ledger, run_id=run_id, out_root=artifact_root,
                out_root_rel=out_root_rel, candidate_set_sha256=candidate_set,
                project_record_id=str(record["record_id"]),
                candidate_members=candidate_members, rust_project_ir=rust_project_ir,
                mapping=mapping, oracle=oracle,
            )
        repair_ready = (
            isinstance(repair, Mapping) and repair.get("status") == "repair-required"
        )
        return {
            "schema_version": 1,
            "artifact_kind": "project-test-semantic-verification",
            "status": "passed" if passed else "repair-required" if repair_ready else "failed",
            "reason_code": None if passed else "project_test_logic_mismatch",
            "blockers": [] if passed or repair_ready else ["project_test_logic_mismatch"],
            "inventory": inventory_ref, "inventory_receipt": inventory_receipt,
            "mapping": mapping_ref, "completeness": completeness_ref,
            "oracle": oracle_ref,
            "gate_observation": gate_observation, "project_gate_record": record,
            **({"candidate_repair": repair} if repair is not None else {}),
            "semantic_gate": False,
        }
    except (ImportError, KeyError, LedgerError, OSError, TypeError, ValueError) as error:
        return _blocked(str(error)[:96] or "project_test_semantic_verification_invalid")


def _run_project_test_oracle(**kwargs: Any) -> dict[str, Any]:
    from .project_test_oracle_runner import run_project_test_oracle

    return run_project_test_oracle(**kwargs)


def _first_blocker(value: Mapping[str, Any], fallback: str) -> str:
    blockers = value.get("blockers")
    if isinstance(blockers, list) and blockers and isinstance(blockers[0], Mapping):
        return str(blockers[0].get("code") or fallback)
    return fallback


def _blocked(code: str, **details: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_kind": "project-test-semantic-verification",
        "status": "blocked", "reason_code": code,
        "blockers": [code], "semantic_gate": False, **details,
    }


__all__ = [
    "reopen_project_test_semantic_evidence", "verify_project_test_semantics",
]
