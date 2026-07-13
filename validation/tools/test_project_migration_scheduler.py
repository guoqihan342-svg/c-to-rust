from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.scheduler import schedule_portfolio


class ProjectMigrationSchedulerTests(unittest.TestCase):
    def test_candidate_review_failure_repair_and_last_good_control_waves(self) -> None:
        portfolio = {
            "limits": {"max_concurrency": 4},
            "assignments": [
                assignment("seed", "translator", 0),
                assignment("seed", "reviewer", 0),
                assignment("seed", "repairer", 0),
                assignment("consumer", "translator", 1, ["seed"]),
            ],
        }
        states = [state("seed"), state("consumer")]
        initial = schedule_portfolio(portfolio, states, {})
        self.assertEqual(["seed-translator"], workers(initial))

        states[0]["status"] = "candidate-ready"
        facts = {"seed": {
            "candidate_artifact_id": "candidate-1",
            "candidate_artifact_sha256": "a" * 64,
        }}
        review = schedule_portfolio(portfolio, states, facts)
        self.assertEqual(["seed-reviewer"], workers(review))

        states[0]["status"] = "retry-ready"
        facts["seed"]["review_artifact_sha256"] = "b" * 64
        facts["seed"]["failed_gate_result_sha256"] = "c" * 64
        repair = schedule_portfolio(portfolio, states, facts)
        self.assertEqual(["seed-repairer"], workers(repair))
        self.assertEqual("candidate_repair", repair["ready"][0]["repair_mode"])

        states[0].update({
            "status": "resume-ready",
            "resumable_status": "last_good",
            "last_good_artifact_id": "candidate-1",
        })
        facts["seed"].pop("failed_gate_result_sha256")
        advanced = schedule_portfolio(portfolio, states, facts)
        self.assertEqual(["consumer-translator"], workers(advanced))
        self.assertFalse(advanced["authority"]["reviewer_can_accept_semantics"])

    def test_hash_bound_planner_decision_is_required_for_boundary_translation(self) -> None:
        planner = assignment("boundary", "planner", 0)
        translator = assignment("boundary", "translator", 0)
        translator["launch_policy"] = {"requires": ["planner_decision_sha256"]}
        portfolio = {
            "limits": {"max_concurrency": 2},
            "assignments": [planner, translator],
        }
        states = [state("boundary")]
        self.assertEqual(["boundary-planner"], workers(
            schedule_portfolio(portfolio, states, {})
        ))

        decision = {
            "run_id": "run",
            "group_id": "boundary",
            "group_sha256": "d" * 64,
            "context_pack_sha256": "e" * 64,
            "decision": "translate_with_context",
        }
        states[0]["status"] = "candidate-ready"
        facts = {"boundary": {
            "planner_decision": decision,
            "planner_decision_sha256": content_sha256(decision),
        }}
        self.assertEqual(["boundary-translator"], workers(
            schedule_portfolio(portfolio, states, facts)
        ))

        facts["boundary"]["planner_decision_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "does not match"):
            schedule_portfolio(portfolio, states, facts)

    def test_concurrency_limit_defers_instead_of_dropping(self) -> None:
        portfolio = {
            "limits": {"max_concurrency": 1},
            "assignments": [
                assignment("one", "translator", 0),
                assignment("two", "translator", 0),
            ],
        }
        result = schedule_portfolio(
            portfolio, [state("one"), state("two")], {}
        )
        self.assertEqual(1, len(result["ready"]))
        self.assertIn("max_concurrency_reached", result["deferred"][0]["reasons"])


def assignment(
    group_id: str, role: str, wave: int, dependencies: list[str] | None = None
) -> dict:
    return {
        "worker_id": f"{group_id}-{role}",
        "run_id": "run",
        "group_id": group_id,
        "unit_id": group_id,
        "group_sha256": "d" * 64,
        "context": {"sha256": "e" * 64},
        "role": role,
        "wave_index": wave,
        "dependencies": dependencies or [],
        "launch_policy": {"requires": []},
    }


def state(group_id: str) -> dict:
    return {
        "group_id": group_id,
        "status": "pending",
        "resumable_status": "ready",
        "last_good_artifact_id": None,
    }


def workers(result: dict) -> list[str]:
    return [item["worker_id"] for item in result["ready"]]


if __name__ == "__main__":
    unittest.main()
