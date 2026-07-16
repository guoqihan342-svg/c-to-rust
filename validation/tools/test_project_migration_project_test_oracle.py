from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.project_test_input_snapshot import (
    materialize_project_test_input_snapshot,
)
from validation.tools._project_migration_harness.project_test_mapping import (
    derive_project_test_mapping,
)
from validation.tools._project_migration_harness.project_test_oracle_evidence import (
    build_project_oracle_evidence,
)
from validation.tools._project_migration_harness.project_test_oracle_snapshot import (
    copy_bounded_repository_snapshot,
)
from validation.tools._project_migration_harness.sandbox_contract import (
    canonical_sha256,
)
from validation.tools.project_migration_rust_project_cargo_v3_test_support import (
    direct_two_package_ir,
)


class ProjectTestOracleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ir, _sources = direct_two_package_ir()
        self.inventory = _inventory()
        self.mapping = derive_project_test_mapping(self.inventory, self.ir)
        self.assertEqual("ready", self.mapping["status"])

    def test_host_comparison_accepts_exact_success(self) -> None:
        oracle = _process(stdout=b"logic-ok\n")
        replay = _process(stdout=b"logic-ok\n", invocation="b" * 64)

        evidence = build_project_oracle_evidence(
            inventory=self.inventory, mapping=self.mapping,
            oracle_results={"test-a": oracle}, replay_results={"test-a": replay},
        )

        self.assertEqual(0, evidence["mismatch_count"])
        self.assertEqual([], evidence["failure_details"])

    def test_host_comparison_reports_bounded_logic_mismatch(self) -> None:
        evidence = build_project_oracle_evidence(
            inventory=self.inventory, mapping=self.mapping,
            oracle_results={"test-a": _process(stdout=b"a")},
            replay_results={"test-a": _process(stdout=b"b", invocation="b" * 64)},
        )

        self.assertEqual(1, evidence["mismatch_count"])
        detail = evidence["failure_details"][0]
        self.assertEqual("61", detail["oracle"]["stdout_prefix_hex"])
        self.assertEqual("62", detail["replay"]["stdout_prefix_hex"])

    def test_blocked_lower_execution_cannot_become_passing_evidence(self) -> None:
        blocked = _process(stdout=b"logic-ok\n", status="blocked")
        evidence = build_project_oracle_evidence(
            inventory=self.inventory, mapping=self.mapping,
            oracle_results={"test-a": _process(stdout=b"logic-ok\n")},
            replay_results={"test-a": blocked},
        )

        self.assertEqual(1, evidence["mismatch_count"])
        self.assertEqual(1, evidence["crash_count"])

    def test_snapshot_hash_commits_empty_directories(self) -> None:
        with tempfile.TemporaryDirectory(prefix="project-snapshot-dir-") as temporary:
            root = Path(temporary)
            first, second = root / "first", root / "second"
            (first / "empty-a").mkdir(parents=True)
            (second / "empty-b").mkdir(parents=True)
            left = copy_bounded_repository_snapshot(first, root / "left-copy")
            right = copy_bounded_repository_snapshot(second, root / "right-copy")

        self.assertNotEqual(left["snapshot_sha256"], right["snapshot_sha256"])

    def test_minimal_input_snapshot_never_includes_source_executable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="project-input-closure-") as temporary:
            root = Path(temporary)
            (root / "build").mkdir()
            binary = root / "build" / "suite"
            binary.write_bytes(b"native")
            inventory = _inventory(
                executable_path="build/suite",
                arguments=[{"kind": "repo-path", "path": "build"}],
            )
            with self.assertRaisesRegex(ValueError, "contains_source_executable"):
                materialize_project_test_input_snapshot(
                    root, root / "snapshot", inventory,
                )


def _process(
    *, stdout: bytes = b"", stderr: bytes = b"", status: str = "completed",
    exit_code: int | None = 0, invocation: str = "a" * 64,
) -> dict:
    invocation_payload = {
        "schema_version": 1, "purpose": "project-test-process",
        "executable_sha256": invocation, "input_sha256": "c" * 64,
        "arguments": ["--mode", "/workspace/fixture.txt"],
        "working_directory": "build", "environment": {"MODE": "portable"},
        "stdin_sha256": hashlib.sha256(b"").hexdigest(),
        "stdin_size_bytes": 0, "timeout_seconds": 30,
        "sandbox_contract_sha256": "d" * 64,
        "sandbox_probe_receipt_sha256": "e" * 64,
    }
    return {
        "schema_version": 1, "artifact_kind": "project-test-process-result",
        "status": status,
        "reason_code": None if status == "completed" else "project_test_process_timed_out",
        "invocation": invocation_payload,
        "invocation_sha256": canonical_sha256(invocation_payload),
        "exit_code": exit_code, "signal": None,
        "timed_out": status == "blocked", "oversized": False,
        "command_started": True,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stdout_size_bytes": len(stdout), "stderr_size_bytes": len(stderr),
        "_stdout": stdout, "_stderr": stderr,
    }


def _inventory(
    *, executable_path: str = "build/suite",
    arguments: list[dict[str, str]] | None = None,
) -> dict:
    test = {
        "source_index": 0, "name": "suite",
        "source_target_id": "build-target-bin",
        "source_executable": {
            "path": executable_path, "kind": "file", "materialized": True,
            "sha256": "a" * 64, "size_bytes": 1,
        },
        "arguments": arguments or [
            {"kind": "literal", "value": "--mode"},
            {"kind": "repo-path", "path": "fixture.txt"},
        ],
        "working_directory": "build",
        "environment": {"MODE": {"kind": "literal", "value": "portable"}},
        "timeout_seconds": 30, "test_id": "test-a",
    }
    value = {
        "schema_version": 1, "artifact_kind": "project-test-inventory",
        "status": "ready", "adapter": "ctest-json-v1",
        "source_observation": {
            "path": "plan/ctest.json", "sha256": "b" * 64,
            "size_bytes": 1,
        },
        "build_directory": "build", "tests": [test], "blockers": [],
        "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        },
    }
    value["inventory_sha256"] = content_sha256(value)
    return value


if __name__ == "__main__":
    unittest.main()
