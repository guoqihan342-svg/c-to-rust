from __future__ import annotations

import hashlib

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.project_test_invocation_commitment import (
    build_project_test_invocation_commitment,
)


def semantic_payloads() -> tuple[dict, dict, dict]:
    inventory = {
        "schema_version": 1,
        "artifact_kind": "project-test-inventory",
        "status": "ready", "adapter": "ctest-json-v1",
        "source_observation": {
            "path": "plan/ctest.json", "sha256": "8" * 64,
            "size_bytes": 80,
        },
        "build_directory": "build",
        "tests": [{"test_id": "test-1"}], "blockers": [],
        "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        },
    }
    inventory["inventory_sha256"] = content_sha256(inventory)
    mapping = {
        "schema_version": 1,
        "artifact_kind": "project-test-mapping",
        "status": "ready",
        "inventory_sha256": inventory["inventory_sha256"],
        "rust_project_ir_sha256": "a" * 64,
        "mappings": [{"source_target_id": "source", "test_ids": ["test-1"]}],
        "blockers": [],
        "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        },
    }
    mapping["mapping_sha256"] = content_sha256(mapping)
    snapshot = {
        "schema_version": 1,
        "artifact_kind": "project-test-input-snapshot",
        "file_count": 0, "directory_count": 1, "size_bytes": 0,
        "files": [], "directories": [{"path": ".", "mode": 493}],
        "required_inputs": [], "working_directories": ["."],
        "source_executables": ["build/test"], "policy": {},
    }
    snapshot["snapshot_sha256"] = content_sha256(snapshot)
    oracle_invocation = build_project_test_invocation_commitment(
        _raw_invocation("b" * 64, snapshot["snapshot_sha256"]),
    )
    replay_invocation = build_project_test_invocation_commitment(
        _raw_invocation("c" * 64, snapshot["snapshot_sha256"]),
    )
    evidence = {
        "schema_version": 3,
        "artifact_kind": "project-test-oracle-evidence",
        "inventory_sha256": inventory["inventory_sha256"],
        "mapping_sha256": mapping["mapping_sha256"],
        "case_count": 1, "mismatch_count": 0, "crash_count": 0,
        "cases": [{
            "test_id": "test-1",
            "oracle_invocation": oracle_invocation,
            "replay_invocation": replay_invocation,
            "oracle_invocation_sha256": oracle_invocation["commitment_sha256"],
            "replay_invocation_sha256": replay_invocation["commitment_sha256"],
            "stdin_sha256": hashlib.sha256(b"").hexdigest(),
            "stdin_size_bytes": 0, "matched": True, "crashed": False,
        }],
        "failure_details": [], "details_truncated": False,
        "semantic_gate": False,
    }
    evidence["evidence_sha256"] = content_sha256(evidence)
    workspace = {
        "schema_version": 1,
        "artifact_kind": "project-test-candidate-workspace",
        "adapter_source_sha256": "d" * 64,
    }
    workspace["workspace_sha256"] = content_sha256(workspace)
    oracle_input_sha = content_sha256({
        "inventory_sha256": inventory["inventory_sha256"],
        "mapping_sha256": mapping["mapping_sha256"],
        "input_snapshot_sha256": snapshot["snapshot_sha256"],
        "workspace_sha256": workspace["workspace_sha256"],
        "evidence_sha256": evidence["evidence_sha256"],
    })
    oracle = {
        "schema_version": 2,
        "artifact_kind": "project-test-oracle-result",
        "status": "passed", "reason_code": None,
        "observation": {
            "case_count": 1, "mismatch_count": 0, "crash_count": 0,
            "oracle_sha256": oracle_input_sha,
            "evidence_sha256": evidence["evidence_sha256"],
            "input_snapshot_sha256": snapshot["snapshot_sha256"],
            "candidate_sha256": "a" * 64,
            "execution_isolation": "independent-oracle-and-replay-sandboxes",
        },
        "evidence": evidence,
        "build": {}, "build_output": {}, "run": {}, "run_output": {},
        "input_snapshot": snapshot, "workspace": workspace,
        "isolation": {
            "shared_read_only_input_snapshot": True,
            "shared_runtime_state": False,
            "source_executable_visible_to_replay": False,
            "comparison_authority": "trusted-host",
        },
        "cleanup_verified": True, "semantic_gate": False,
    }
    return inventory, mapping, oracle


def _raw_invocation(executable_sha256: str, input_sha256: str) -> dict:
    return {
        "schema_version": 1, "purpose": "project-test-process",
        "executable_sha256": executable_sha256,
        "input_sha256": input_sha256,
        "arguments": [], "working_directory": "build", "environment": {},
        "stdin_sha256": hashlib.sha256(b"").hexdigest(),
        "stdin_size_bytes": 0, "timeout_seconds": 30,
        "sandbox_contract_sha256": "d" * 64,
        "sandbox_probe_receipt_sha256": "e" * 64,
    }


__all__ = ["semantic_payloads"]
