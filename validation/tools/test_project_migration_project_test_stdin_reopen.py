from __future__ import annotations

import copy
import hashlib
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.project_test_oracle_case_binding import (
    validate_passed_project_oracle_evidence,
)
from validation.tools._project_migration_harness.project_test_invocation_commitment import (
    build_project_test_invocation_commitment,
)


class ProjectTestStdinReopenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory, self.snapshot, self.evidence = _payloads()

    def test_v3_evidence_reopens_with_exact_snapshot_stdin(self) -> None:
        validate_passed_project_oracle_evidence(
            self.evidence, self.inventory, self.snapshot,
        )

    def test_missing_or_drifted_stdin_evidence_fails_closed(self) -> None:
        mutations = {
            "missing-size": lambda case: case.pop("stdin_size_bytes"),
            "wrong-size": lambda case: case.update(stdin_size_bytes=8),
            "wrong-sha": lambda case: case.update(stdin_sha256="f" * 64),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                evidence = copy.deepcopy(self.evidence)
                mutate(evidence["cases"][0])
                _rehash(evidence, "evidence_sha256")
                with self.assertRaises(ValueError):
                    validate_passed_project_oracle_evidence(
                        evidence, self.inventory, self.snapshot,
                    )

    def test_inventory_stdin_path_must_exist_in_snapshot_manifest(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["tests"][0]["stdin"]["path"] = "other.bin"
        _rehash(inventory, "inventory_sha256")
        evidence = copy.deepcopy(self.evidence)
        evidence["inventory_sha256"] = inventory["inventory_sha256"]
        _rehash(evidence, "evidence_sha256")

        with self.assertRaisesRegex(ValueError, "stdin_snapshot_invalid"):
            validate_passed_project_oracle_evidence(
                evidence, inventory, self.snapshot,
            )

    def test_invocation_commitment_cannot_claim_different_stdin(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        case = evidence["cases"][0]
        commitment = build_project_test_invocation_commitment(
            _raw_invocation(
                "b" * 64, self.snapshot["snapshot_sha256"],
                "f" * 64, case["stdin_size_bytes"],
            ),
        )
        case["oracle_invocation"] = commitment
        case["oracle_invocation_sha256"] = commitment["commitment_sha256"]
        _rehash(evidence, "evidence_sha256")

        with self.assertRaisesRegex(ValueError, "case_stdin_drifted"):
            validate_passed_project_oracle_evidence(
                evidence, self.inventory, self.snapshot,
            )

    def test_legacy_v2_reopens_only_when_inventory_has_no_stdin(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["schema_version"] = 2
        evidence["cases"][0].pop("oracle_invocation")
        evidence["cases"][0].pop("replay_invocation")
        evidence["cases"][0].pop("stdin_sha256")
        evidence["cases"][0].pop("stdin_size_bytes")
        _rehash(evidence, "evidence_sha256")
        with self.assertRaisesRegex(ValueError, "legacy_stdin_unbound"):
            validate_passed_project_oracle_evidence(
                evidence, self.inventory, self.snapshot,
            )

        inventory = copy.deepcopy(self.inventory)
        inventory["tests"][0].pop("stdin")
        _rehash(inventory, "inventory_sha256")
        evidence["inventory_sha256"] = inventory["inventory_sha256"]
        _rehash(evidence, "evidence_sha256")
        validate_passed_project_oracle_evidence(
            evidence, inventory, self.snapshot,
        )


def _payloads() -> tuple[dict, dict, dict]:
    data = b"bound-stdin\x00\xff\n"
    digest = hashlib.sha256(data).hexdigest()
    inventory = {
        "schema_version": 1, "artifact_kind": "project-test-inventory",
        "status": "ready", "adapter": "make-dry-run-v1",
        "tests": [{
            "test_id": "test-a",
            "stdin": {"kind": "repo-path", "path": "fixture.bin"},
        }],
    }
    _rehash(inventory, "inventory_sha256")
    snapshot = {
        "schema_version": 1,
        "artifact_kind": "project-test-input-snapshot",
        "file_count": 1, "directory_count": 1, "size_bytes": len(data),
        "files": [{
            "path": "fixture.bin", "sha256": digest,
            "size_bytes": len(data), "mode": 0o600,
        }],
        "directories": [{"path": ".", "mode": 0o700}],
        "required_inputs": ["fixture.bin"], "working_directories": ["."],
        "source_executables": ["build/suite"], "policy": {},
    }
    _rehash(snapshot, "snapshot_sha256")
    oracle_invocation = build_project_test_invocation_commitment(
        _raw_invocation("b" * 64, snapshot["snapshot_sha256"], digest, len(data)),
    )
    replay_invocation = build_project_test_invocation_commitment(
        _raw_invocation("c" * 64, snapshot["snapshot_sha256"], digest, len(data)),
    )
    evidence = {
        "schema_version": 3,
        "artifact_kind": "project-test-oracle-evidence",
        "inventory_sha256": inventory["inventory_sha256"],
        "mapping_sha256": "a" * 64,
        "case_count": 1, "mismatch_count": 0, "crash_count": 0,
        "cases": [{
            "test_id": "test-a",
            "oracle_invocation": oracle_invocation,
            "replay_invocation": replay_invocation,
            "oracle_invocation_sha256": oracle_invocation["commitment_sha256"],
            "replay_invocation_sha256": replay_invocation["commitment_sha256"],
            "stdin_sha256": digest, "stdin_size_bytes": len(data),
            "matched": True, "crashed": False,
        }],
        "failure_details": [], "details_truncated": False,
        "semantic_gate": False,
    }
    _rehash(evidence, "evidence_sha256")
    return inventory, snapshot, evidence


def _raw_invocation(
    executable_sha256: str, input_sha256: str,
    stdin_sha256: str, stdin_size_bytes: int,
) -> dict:
    return {
        "schema_version": 1, "purpose": "project-test-process",
        "executable_sha256": executable_sha256, "input_sha256": input_sha256,
        "arguments": ["--strict"], "working_directory": "build",
        "environment": {}, "stdin_sha256": stdin_sha256,
        "stdin_size_bytes": stdin_size_bytes, "timeout_seconds": 30,
        "sandbox_contract_sha256": "d" * 64,
        "sandbox_probe_receipt_sha256": "e" * 64,
    }


def _rehash(value: dict, field: str) -> None:
    value[field] = content_sha256({
        key: item for key, item in value.items() if key != field
    })


if __name__ == "__main__":
    unittest.main()
