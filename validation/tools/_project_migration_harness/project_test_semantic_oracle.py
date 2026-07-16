from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .ledger import LedgerError
from .project_test_oracle_case_binding import (
    validate_passed_project_oracle_evidence,
)


def validate_passed_project_test_oracle(
    oracle: Mapping[str, Any], inventory: Mapping[str, Any],
    mapping: Mapping[str, Any], completeness: Mapping[str, Any],
) -> Mapping[str, Any]:
    observation, evidence = oracle.get("observation"), oracle.get("evidence")
    if (
        oracle.get("artifact_kind") != "project-test-oracle-result"
        or oracle.get("status") != "passed" or oracle.get("reason_code") is not None
        or oracle.get("cleanup_verified") is not True
        or oracle.get("semantic_gate") is not False
        or not isinstance(observation, Mapping) or not isinstance(evidence, Mapping)
        or evidence.get("inventory_sha256") != inventory.get("inventory_sha256")
        or evidence.get("mapping_sha256") != mapping.get("mapping_sha256")
        or evidence.get("completeness_sha256")
        != completeness.get("completeness_sha256")
        or evidence.get("evidence_sha256") != content_sha256({
            key: value for key, value in evidence.items() if key != "evidence_sha256"
        })
        or observation.get("case_count") != len(inventory["tests"])
        or observation.get("mismatch_count") != 0
        or observation.get("crash_count") != 0
        or observation.get("candidate_sha256")
        != mapping.get("rust_project_ir_sha256")
    ):
        raise LedgerError("project_test_oracle_summary_invalid")
    if oracle.get("schema_version") != 2:
        raise LedgerError("project_test_oracle_schema_version_invalid")
    _validate_v2(
        oracle, observation, evidence, inventory, mapping, completeness,
    )
    return observation


def _validate_v2(
    oracle: Mapping[str, Any], observation: Mapping[str, Any],
    evidence: Mapping[str, Any], inventory: Mapping[str, Any],
    mapping: Mapping[str, Any], completeness: Mapping[str, Any],
) -> None:
    snapshot, workspace, isolation = (
        oracle.get("input_snapshot"), oracle.get("workspace"),
        oracle.get("isolation"),
    )
    expected_isolation = {
        "shared_read_only_input_snapshot": True, "shared_runtime_state": False,
        "source_executable_visible_to_replay": False,
        "comparison_authority": "trusted-host",
    }
    if (
        evidence.get("schema_version") != 4
        or evidence.get("artifact_kind") != "project-test-oracle-evidence"
        or not isinstance(snapshot, Mapping) or not isinstance(workspace, Mapping)
        or snapshot.get("snapshot_sha256") != content_sha256({
            key: value for key, value in snapshot.items() if key != "snapshot_sha256"
        })
        or workspace.get("workspace_sha256") != content_sha256({
            key: value for key, value in workspace.items() if key != "workspace_sha256"
        })
        or workspace.get("inventory_sha256") != inventory.get("inventory_sha256")
        or workspace.get("mapping_sha256") != mapping.get("mapping_sha256")
        or workspace.get("completeness_sha256")
        != completeness.get("completeness_sha256")
        or observation.get("evidence_sha256") != evidence.get("evidence_sha256")
        or observation.get("completeness_sha256")
        != completeness.get("completeness_sha256")
        or observation.get("input_snapshot_sha256") != snapshot.get("snapshot_sha256")
        or observation.get("execution_isolation")
        != "independent-oracle-and-replay-sandboxes"
        or isolation != expected_isolation
        or observation.get("oracle_sha256") != content_sha256({
            "inventory_sha256": inventory["inventory_sha256"],
            "mapping_sha256": mapping["mapping_sha256"],
            "completeness_sha256": completeness["completeness_sha256"],
            "input_snapshot_sha256": snapshot["snapshot_sha256"],
            "workspace_sha256": workspace["workspace_sha256"],
            "evidence_sha256": evidence["evidence_sha256"],
        })
    ):
        raise LedgerError("project_test_oracle_v2_binding_invalid")
    try:
        validate_passed_project_oracle_evidence(
            evidence, inventory, snapshot, completeness,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise LedgerError("project_test_oracle_case_binding_invalid") from error


__all__ = ["validate_passed_project_test_oracle"]
