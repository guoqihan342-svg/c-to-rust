from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools._project_migration_harness.artifacts import (
    content_sha256, write_json_artifact,
)
from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)
from validation.tools._project_migration_harness.ledger import LedgerError
from validation.tools._project_migration_harness.project_host_gates import (
    record_host_project_observation,
)
from validation.tools._project_migration_harness.project_test_semantic_verifier import (
    reopen_project_test_semantic_evidence, verify_project_test_semantics,
)
from validation.tools.project_migration_gate_authority_test_support import (
    ProjectMigrationGateAuthorityCase,
)


MODULE = (
    "validation.tools._project_migration_harness."
    "project_test_semantic_verifier."
)


class ProjectTestSemanticVerifierArtifactTests(unittest.TestCase):
    def test_oracle_result_is_content_addressed_and_gate_binds_its_sha(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-test-artifact-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        artifacts = root / "target" / "run"
        artifacts.mkdir(parents=True)
        inventory, mapping, oracle = _payloads()
        inventory_ref = write_json_artifact(
            artifacts, "plan/project-test-inventory.json", inventory,
        )
        manifest = {
            "project_test_inventory": {
                "status": "bound", "artifact": inventory_ref,
            },
        }
        ledger = mock.Mock()
        ledger.bind_current_candidate_set.return_value = "f" * 64
        record = {
            "gate_status": "passed", "record_id": "oracle-record",
        }
        with (
            mock.patch(MODULE + "load_managed_project_context", return_value={
                "generation_root": root / "generation",
                "rust_project_ir": {"ir_sha256": "a" * 64},
            }),
            mock.patch(
                MODULE + "reopen_manifest_project_test_inventory",
                return_value=inventory,
            ),
            mock.patch(MODULE + "derive_project_test_mapping", return_value=mapping),
            mock.patch(MODULE + "_run_project_test_oracle", return_value=oracle),
            mock.patch(
                MODULE + "record_host_project_observation", return_value=record,
            ) as gate_recorder,
        ):
            result = verify_project_test_semantics(
                ledger=ledger, run_id="run", repo_root=root,
                artifact_root=artifacts, out_root_rel="target/run",
                project_root=root, runtime_root=root / "runtime",
                migration_manifest=manifest, candidate_members=[],
            )

        self.assertEqual("passed", result["status"])
        oracle_ref = result["oracle"]
        self.assertEqual(
            f"verification/project-test/oracle/{oracle_ref['sha256']}.json",
            oracle_ref["path"],
        )
        stored = json.loads(
            (artifacts / oracle_ref["path"]).read_text(encoding="utf-8"),
        )
        self.assertEqual(oracle, stored)
        observed = gate_recorder.call_args.kwargs["observation"]
        self.assertEqual(oracle_ref["sha256"], observed["oracle_sha256"])
        self.assertNotEqual(
            oracle["observation"]["oracle_sha256"], observed["oracle_sha256"],
        )


class ProjectTestSemanticEvidenceReopenTests(ProjectMigrationGateAuthorityCase):
    def setUp(self) -> None:
        super().setUp()
        self.promote_current_candidate()
        self.candidate_set = self.ledger.bind_current_candidate_set(run_id="run")
        self.inventory, self.mapping, self.oracle = _payloads()
        self.inventory_ref = write_json_artifact(
            self.out_root, "plan/project-test-inventory.json", self.inventory,
        )
        self.mapping_ref = write_json_artifact(
            self.out_root, "completion/project-test-mapping.json", self.mapping,
        )
        self.oracle_ref = write_content_addressed_json(
            self.out_root, "project-test/oracle", self.oracle,
        )
        self.gate_observation = {
            "case_count": 1, "mismatch_count": 0, "crash_count": 0,
            "oracle_sha256": self.oracle_ref["sha256"],
            "candidate_sha256": "a" * 64,
        }
        self.record = record_host_project_observation(
            ledger=self.ledger, out_root=self.out_root,
            out_root_rel="target/run", run_id="run",
            gate_kind="oracle-replay",
            candidate_set_sha256=self.candidate_set,
            observation=self.gate_observation,
        )
        self.verification = {
            "schema_version": 1,
            "artifact_kind": "project-test-semantic-verification",
            "status": "passed", "reason_code": None, "blockers": [],
            "inventory": self.inventory_ref, "mapping": self.mapping_ref,
            "oracle": self.oracle_ref,
            "gate_observation": self.gate_observation,
            "project_gate_record": self.record,
            "semantic_gate": False,
        }

    def test_reopen_recomputes_summary_and_preserves_exact_refs(self) -> None:
        result = self._reopen(self.verification)
        self.assertEqual("verified", result["status"])
        self.assertEqual(self.inventory_ref, result["inventory"])
        self.assertEqual(self.mapping_ref, result["mapping"])
        self.assertEqual(self.oracle_ref, result["oracle"])
        summary = result["summary"]
        expected = {
            key: value for key, value in summary.items()
            if key != "summary_sha256"
        }
        self.assertEqual(content_sha256(expected), summary["summary_sha256"])
        self.assertFalse(result["semantic_gate"])

    def test_overwritten_oracle_artifact_fails_closed(self) -> None:
        (self.out_root / self.oracle_ref["path"]).write_text(
            "{}\n", encoding="utf-8",
        )
        with self.assertRaisesRegex(
            LedgerError, "project_test_oracle_artifact_drifted",
        ):
            self._reopen(self.verification)

    def test_overwritten_inventory_artifact_fails_closed(self) -> None:
        (self.out_root / self.inventory_ref["path"]).write_text(
            "{}\n", encoding="utf-8",
        )
        with self.assertRaisesRegex(
            LedgerError, "project_test_inventory_artifact_drifted",
        ):
            self._reopen(self.verification)

    def test_overwritten_mapping_artifact_fails_closed(self) -> None:
        (self.out_root / self.mapping_ref["path"]).write_text(
            "{}\n", encoding="utf-8",
        )
        with self.assertRaisesRegex(
            LedgerError, "project_test_mapping_artifact_drifted",
        ):
            self._reopen(self.verification)

    def test_overwritten_host_gate_observation_fails_closed(self) -> None:
        raw_ref = self.record["raw_observation"]
        (self.harness / raw_ref["path"]).write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(
            LedgerError, "project_test_raw_observation_artifact_drifted",
        ):
            self._reopen(self.verification)

    def test_overwritten_host_gate_summary_fails_closed(self) -> None:
        evidence_ref = self.record["evidence"]
        (self.harness / evidence_ref["path"]).write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(
            LedgerError, "project_test_gate_evidence_artifact_drifted",
        ):
            self._reopen(self.verification)

    def test_gate_observation_no_longer_matching_oracle_ref_fails_closed(self) -> None:
        changed = copy.deepcopy(self.verification)
        changed["gate_observation"]["oracle_sha256"] = "b" * 64
        with self.assertRaisesRegex(
            LedgerError, "project_test_gate_observation_binding_drifted",
        ):
            self._reopen(changed)

    def _reopen(self, verification: dict) -> dict:
        return reopen_project_test_semantic_evidence(
            ledger=self.ledger, artifact_root=self.out_root,
            out_root_rel="target/run", run_id="run",
            candidate_set_sha256=self.candidate_set,
            verification=verification,
        )


def _payloads() -> tuple[dict, dict, dict]:
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
    evidence = {
        "schema_version": 2,
        "artifact_kind": "project-test-oracle-evidence",
        "inventory_sha256": inventory["inventory_sha256"],
        "mapping_sha256": mapping["mapping_sha256"],
        "case_count": 1, "mismatch_count": 0, "crash_count": 0,
        "cases": [{
            "test_id": "test-1", "oracle_invocation_sha256": "b" * 64,
            "replay_invocation_sha256": "c" * 64,
            "matched": True, "crashed": False,
        }],
        "failure_details": [], "details_truncated": False,
        "semantic_gate": False,
    }
    evidence["evidence_sha256"] = content_sha256(evidence)
    snapshot = {
        "schema_version": 1,
        "artifact_kind": "project-test-input-snapshot",
        "file_count": 0, "directory_count": 1, "size_bytes": 0,
        "files": [], "directories": [{"path": ".", "mode": 493}],
        "required_inputs": [], "working_directories": ["."],
        "source_executables": ["build/test"], "policy": {},
    }
    snapshot["snapshot_sha256"] = content_sha256(snapshot)
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


if __name__ == "__main__":
    unittest.main()
