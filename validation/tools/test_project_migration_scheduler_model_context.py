from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.scheduler import schedule_portfolio


class ProjectMigrationSchedulerModelContextTests(unittest.TestCase):
    def test_model_safe_test_contract_reaches_translation_roles_only(self) -> None:
        portfolio = {
            "limits": {"max_concurrency": 2},
            "assignments": [
                assignment("alpha", "translator"),
                assignment("beta", "reviewer"),
            ],
        }
        states = [state("alpha", "pending"), state("beta", "candidate-ready")]
        reference = {
            "path": "target/run/plan/test-contract.json",
            "sha256": "a" * 64,
            "size_bytes": 123,
        }
        facts = {
            "alpha": {"model_safe_test_contract": reference},
            "beta": {
                "model_safe_test_contract": reference,
                "candidate_artifact": reference | {"artifact_id": "candidate-beta"},
                "candidate_artifact_id": "candidate-beta",
                "candidate_artifact_sha256": "a" * 64,
            },
        }

        result = schedule_portfolio(portfolio, states, facts)

        by_role = {item["role"]: item for item in result["ready"]}
        self.assertEqual(
            reference,
            by_role["translator"]["input_facts"]["model_safe_test_contract"],
        )
        self.assertNotIn(
            "model_safe_test_contract", by_role["reviewer"]["input_facts"],
        )


def assignment(group_id: str, role: str) -> dict:
    return {
        "worker_id": f"{group_id}-{role}", "run_id": "run",
        "group_id": group_id, "unit_id": group_id,
        "group_sha256": "d" * 64, "context": {"sha256": "e" * 64},
        "role": role, "wave_index": 0, "dependencies": [],
        "launch_policy": {"requires": []},
    }


def state(group_id: str, status: str) -> dict:
    return {
        "group_id": group_id, "status": status,
        "resumable_status": "ready", "last_good_artifact_id": None,
    }


if __name__ == "__main__":
    unittest.main()
