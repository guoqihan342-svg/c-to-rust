from __future__ import annotations

import json
import unittest
from unittest import mock

from validation.tools._project_migration_harness.project_test_semantic_repair import (
    model_safe_project_failure_diagnostics,
    register_project_test_candidate_repairs,
)


class ProjectTestSemanticRepairTests(unittest.TestCase):
    def test_failed_target_attribution_queues_every_owning_unit_atomically(self) -> None:
        ledger = mock.Mock()
        ir = {
            "targets": [{
                "build_ir_target_id": "source-bin",
                "module_ids": ["module-a", "module-b"],
            }],
            "modules": [
                {"module_id": "module-a", "unit_id": "unit-a"},
                {"module_id": "module-b", "unit_id": "unit-b"},
            ],
        }
        mapping = {"mappings": [{
            "source_target_id": "source-bin", "test_ids": ["test-a"],
        }]}
        oracle = {
            "observation": {"crash_count": 0},
            "evidence": {
                "failure_details": [{"test_id": "test-a"}],
                "details_truncated": False,
            },
        }
        members = [
            {"unit_id": "unit-a", "artifact_id": "candidate-a"},
            {"unit_id": "unit-b", "artifact_id": "candidate-b"},
        ]
        with mock.patch(
            "validation.tools._project_migration_harness."
            "project_test_semantic_repair.record_candidate_gate",
            side_effect=lambda **values: {"record_id": values["record_id"]},
        ) as record:
            result = register_project_test_candidate_repairs(
                ledger=ledger, run_id="run", out_root=mock.Mock(),
                out_root_rel="out", candidate_set_sha256="a" * 64,
                project_record_id="host-oracle-record",
                candidate_members=members, rust_project_ir=ir,
                mapping=mapping, oracle=oracle,
            )

        self.assertEqual("repair-required", result["status"])
        self.assertEqual(["unit-a", "unit-b"], result["affected_unit_ids"])
        self.assertEqual(2, record.call_count)
        self.assertTrue(all(
            call.kwargs["defer_transition"] for call in record.call_args_list
        ))
        failures = ledger.mark_verification_failures.call_args.kwargs["failures"]
        self.assertEqual(["unit-a", "unit-b"], [item["unit_id"] for item in failures])

    def test_truncated_details_conservatively_repair_all_mapped_targets(self) -> None:
        ledger = mock.Mock()
        ir = {
            "targets": [
                {"build_ir_target_id": "a", "module_ids": ["ma"]},
                {"build_ir_target_id": "b", "module_ids": ["mb"]},
            ],
            "modules": [
                {"module_id": "ma", "unit_id": "ua"},
                {"module_id": "mb", "unit_id": "ub"},
            ],
        }
        mapping = {"mappings": [
            {"source_target_id": "a", "test_ids": ["ta"]},
            {"source_target_id": "b", "test_ids": ["tb"]},
        ]}
        oracle = {
            "observation": {"crash_count": 1},
            "evidence": {
                "failure_details": [{"test_id": "ta"}],
                "details_truncated": True,
            },
        }
        members = [
            {"unit_id": "ua", "artifact_id": "ca"},
            {"unit_id": "ub", "artifact_id": "cb"},
        ]
        with mock.patch(
            "validation.tools._project_migration_harness."
            "project_test_semantic_repair.record_candidate_gate",
            return_value={},
        ):
            result = register_project_test_candidate_repairs(
                ledger=ledger, run_id="run", out_root=mock.Mock(),
                out_root_rel="out", candidate_set_sha256="a" * 64,
                project_record_id="record", candidate_members=members,
                rust_project_ir=ir, mapping=mapping, oracle=oracle,
            )
        self.assertEqual(["ua", "ub"], result["affected_unit_ids"])

    def test_failed_executable_attributes_dependency_package_units(self) -> None:
        ledger = mock.Mock()
        ir = {
            "targets": [{
                "build_ir_target_id": "source-bin", "package_id": "app",
                "module_ids": ["test-main"],
            }],
            "packages": [
                {
                    "package_id": "app", "module_ids": ["test-main"],
                    "dependency_package_ids": ["library"],
                },
                {
                    "package_id": "library", "module_ids": ["implementation"],
                    "dependency_package_ids": ["core"],
                },
                {
                    "package_id": "core", "module_ids": ["core-module"],
                    "dependency_package_ids": [],
                },
                {
                    "package_id": "unrelated", "module_ids": ["unrelated-module"],
                    "dependency_package_ids": [],
                },
            ],
            "modules": [
                {"module_id": "test-main", "unit_id": "test-unit"},
                {"module_id": "implementation", "unit_id": "library-unit"},
                {"module_id": "core-module", "unit_id": "core-unit"},
                {"module_id": "unrelated-module", "unit_id": "unrelated-unit"},
            ],
        }
        mapping = {"mappings": [{
            "source_target_id": "source-bin", "test_ids": ["test-a"],
        }]}
        oracle = {"evidence": {
            "failure_details": [{"test_id": "test-a"}],
            "details_truncated": False,
        }}
        members = [
            {"unit_id": "test-unit", "artifact_id": "test-candidate"},
            {"unit_id": "library-unit", "artifact_id": "library-candidate"},
            {"unit_id": "core-unit", "artifact_id": "core-candidate"},
            {"unit_id": "unrelated-unit", "artifact_id": "unrelated-candidate"},
        ]

        with mock.patch(
            "validation.tools._project_migration_harness."
            "project_test_semantic_repair.record_candidate_gate",
            return_value={},
        ):
            result = register_project_test_candidate_repairs(
                ledger=ledger, run_id="run", out_root=mock.Mock(),
                out_root_rel="out", candidate_set_sha256="a" * 64,
                project_record_id="record", candidate_members=members,
                rust_project_ir=ir, mapping=mapping, oracle=oracle,
            )

        self.assertEqual(
            ["core-unit", "library-unit", "test-unit"],
            result["affected_unit_ids"],
        )

    def test_failure_signature_exposes_channels_without_answer_values(self) -> None:
        oracle = {
            "observation": {"crash_count": 1},
            "evidence": {"failure_details": [{
                "test_id": "test-a",
                "oracle": {
                    "status": "completed", "exit_code": 0, "signal": None,
                    "timed_out": False, "oversized": False,
                    "stdout_sha256": "a" * 64, "stderr_sha256": "b" * 64,
                    "stdout_prefix_hex": "expected-secret",
                },
                "replay": {
                    "status": "completed", "exit_code": 7, "signal": None,
                    "timed_out": False, "oversized": False,
                    "stdout_sha256": "c" * 64, "stderr_sha256": "b" * 64,
                    "stdout_prefix_hex": "actual-secret",
                },
            }]},
        }

        diagnostics = model_safe_project_failure_diagnostics(oracle)

        self.assertEqual(
            [
                {"code": "project-channel.exit", "stage": "project-oracle"},
                {"code": "project-channel.stdout", "stage": "project-oracle"},
                {"code": "project-process.nonzero-exit", "stage": "project-oracle"},
            ],
            diagnostics,
        )
        encoded = json.dumps(diagnostics, sort_keys=True)
        self.assertNotIn("expected-secret", encoded)
        self.assertNotIn("actual-secret", encoded)
        self.assertNotIn("a" * 64, encoded)


if __name__ == "__main__":
    unittest.main()
