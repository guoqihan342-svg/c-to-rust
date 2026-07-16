from __future__ import annotations

import unittest
from unittest import mock

from validation.tools._project_migration_harness.gate_candidate_sets import (
    candidate_set_members,
)
from validation.tools._project_migration_harness.ledger import LedgerError
from validation.tools._project_migration_harness.project_candidate_gate_aggregation import (
    record_project_candidate_aggregate_gates,
)
from validation.tools.project_migration_gate_authority_test_support import (
    ProjectMigrationGateAuthorityCase,
)


class ProjectCandidateGateAggregationTests(ProjectMigrationGateAuthorityCase):
    def test_current_strict_candidate_gates_become_project_gates(self) -> None:
        self.promote_current_candidate()
        candidate_set = self.ledger.bind_current_candidate_set(run_id="run")
        with self.ledger.connect() as connection:
            members = candidate_set_members(connection, "run", candidate_set)

        aggregates = {
            "negative_case_count": 2, "unexpected_accept_count": 0,
            "unsafe_abi_check_count": 2, "unsafe_abi_violation_count": 0,
        }
        with mock.patch(
            "validation.tools._project_migration_harness."
            "project_candidate_gate_aggregation._validated_aggregates",
            return_value=aggregates,
        ):
            result = record_project_candidate_aggregate_gates(
                ledger=self.ledger, run_id="run", out_root=self.out_root,
                out_root_rel="target/run",
                candidate_set_sha256=candidate_set,
                candidate_members=members,
            )

        self.assertEqual("passed", result["status"])
        self.assertGreater(result["aggregates"]["negative_case_count"], 0)
        self.assertGreater(result["aggregates"]["unsafe_abi_check_count"], 0)
        self.assertEqual(0, result["aggregates"]["unexpected_accept_count"])
        self.assertEqual(0, result["aggregates"]["unsafe_abi_violation_count"])
        self.assertEqual(
            "passed",
            result["project_gate_records"]["negative"]["gate_status"],
        )
        self.assertEqual(
            "passed",
            result["project_gate_records"]["unsafe_alias_abi"]["gate_status"],
        )

    def test_caller_cannot_omit_candidate_set_members(self) -> None:
        self.promote_current_candidate()
        candidate_set = self.ledger.bind_current_candidate_set(run_id="run")

        with self.assertRaisesRegex(LedgerError, "cohort drifted"):
            record_project_candidate_aggregate_gates(
                ledger=self.ledger, run_id="run", out_root=self.out_root,
                out_root_rel="target/run",
                candidate_set_sha256=candidate_set,
                candidate_members=[],
            )


if __name__ == "__main__":
    unittest.main()
