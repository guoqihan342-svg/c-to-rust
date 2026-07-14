from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.scheduler import schedule_portfolio
from validation.tools.project_migration_controller_test_support import (
    ProjectMigrationControllerCase,
)


class PendingRetrievalSchedulerTests(unittest.TestCase):
    def test_pending_retrieval_defers_planner_and_translator_before_role_checks(self) -> None:
        retrieval = {
            "selection_status": "blocked",
            "selection_receipt_sha256": "a" * 64,
            "selection_blockers": ["required_fact_unresolved"],
        }
        assignments = [
            _assignment("boundary", role, retrieval)
            for role in ("planner", "translator")
        ]

        result = schedule_portfolio(
            {"limits": {"max_concurrency": 2}, "assignments": assignments},
            [_state("boundary")],
            {},
        )

        self.assertEqual([], result["ready"])
        self.assertEqual(2, len(result["deferred"]))
        self.assertTrue(all(
            item["reasons"] == ["context_retrieval_pending"]
            for item in result["deferred"]
        ))


class PendingRetrievalDispatchTests(ProjectMigrationControllerCase):
    def test_pending_retrieval_creates_no_attempt_lease_or_model_launch(self) -> None:
        plan = self.plan("int unit(void) { return external_api(); }\n")
        ledger = self.ledger()

        dispatched = self.dispatch(plan, ledger)

        self.assertEqual([], dispatched["launches"])
        self.assertEqual("waiting", dispatched["status"])
        self.assertFalse(dispatched["execution"]["model_launched"])
        self.assertTrue(all(
            item["reasons"] == ["context_retrieval_pending"]
            for item in dispatched["deferred"]
        ))
        with ledger.connect() as connection:
            attempts = connection.execute(
                "select count(*) from attempts where run_id=?", (plan["run_id"],)
            ).fetchone()[0]
            leases = connection.execute(
                "select count(*) from leases where run_id=?", (plan["run_id"],)
            ).fetchone()[0]
        self.assertEqual((0, 0), (attempts, leases))


def _assignment(group_id: str, role: str, retrieval: dict) -> dict:
    return {
        "worker_id": f"{group_id}-{role}",
        "run_id": "run",
        "group_id": group_id,
        "unit_id": group_id,
        "group_sha256": "d" * 64,
        "context": {"sha256": "e" * 64, "retrieval": retrieval},
        "role": role,
        "wave_index": 0,
        "dependencies": [],
        "launch_policy": {"requires": []},
    }


def _state(group_id: str) -> dict:
    return {
        "group_id": group_id,
        "status": "pending",
        "resumable_status": "ready",
        "last_good_artifact_id": None,
    }


if __name__ == "__main__":
    unittest.main()
