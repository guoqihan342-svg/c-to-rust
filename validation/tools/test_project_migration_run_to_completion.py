from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools._project_migration_harness.project_run_to_completion import (
    run_project_to_completion,
)


MODULE = (
    "validation.tools._project_migration_harness."
    "project_run_to_completion."
)


class ProjectRunToCompletionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-run-completion-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out_root = self.root / "target" / "run"
        self.out_root.mkdir(parents=True)
        self.arguments = {
            "ledger": mock.Mock(), "harness_root": self.root,
            "repo_root": self.root, "out_root": self.out_root,
            "out_root_rel": "target/run", "max_cycles": 4,
        }
        self.portfolio = {"run_id": "run"}
        self.preflight = {
            "status": "passed",
            "report": {"path": "target/run/preflight.json", "sha256": "a" * 64},
        }

    def test_waiting_run_dispatches_worker_then_reaches_completion(self) -> None:
        waiting = {
            "status": "waiting", "stage": "candidate-worker-required",
            "checkpoint_sha256": "b" * 64,
        }
        completed = {
            "status": "completed", "semantic_gate": True,
            "completion_receipt": {"sha256": "c" * 64},
        }
        dispatch = {
            "status": "dispatched", "dispatch_sha256": "d" * 64,
            "deferred": [], "launches": [{
                "worker_id": "repairer", "unit_id": "unit",
                "attempt_id": "attempt", "request": {
                    "path": "target/run/request.json", "sha256": "e" * 64,
                },
            }],
        }
        with (
            mock.patch(
                MODULE + "resume_project_completion",
                side_effect=[waiting, completed],
            ) as completion,
            mock.patch(
                MODULE + "run_project_worker_preflight",
                return_value=self.preflight,
            ) as preflight,
            mock.patch(
                MODULE + "dispatch_project_workers", return_value=dispatch,
            ) as dispatcher,
            mock.patch(
                MODULE + "run_and_ingest_opencode_worker",
                return_value={"status": "candidate-ready"},
            ) as worker,
        ):
            result = run_project_to_completion(
                self.portfolio, **self.arguments,
            )

        self.assertEqual("completed", result["status"])
        self.assertTrue(result["semantic_gate"])
        self.assertEqual(2, completion.call_count)
        preflight.assert_called_once()
        dispatcher.assert_called_once()
        worker.assert_called_once()

    def test_already_completable_run_does_not_probe_model(self) -> None:
        with (
            mock.patch(
                MODULE + "resume_project_completion",
                return_value={"status": "completed", "semantic_gate": True},
            ),
            mock.patch(MODULE + "run_project_worker_preflight") as preflight,
        ):
            result = run_project_to_completion(
                self.portfolio, **self.arguments,
            )
        self.assertEqual("completed", result["status"])
        self.assertIsNone(result["preflight"])
        preflight.assert_not_called()

    def test_project_logic_mismatch_repairs_reviews_and_completes(self) -> None:
        completions = [{
            "status": "waiting",
            "stage": "project-final-semantic-repair-ready",
        }, {
            "status": "waiting", "stage": "candidate-worker-required",
        }, {
            "status": "completed", "semantic_gate": True,
        }]
        dispatches = [{
            "status": "dispatched", "dispatch_sha256": "1" * 64,
            "deferred": [], "launches": [{
                "worker_id": "repairer", "unit_id": "unit",
                "attempt_id": "repair-attempt",
                "request": {"path": "target/run/repair.json", "sha256": "2" * 64},
            }],
        }, {
            "status": "dispatched", "dispatch_sha256": "3" * 64,
            "deferred": [], "launches": [{
                "worker_id": "reviewer", "unit_id": "unit",
                "attempt_id": "review-attempt",
                "request": {"path": "target/run/review.json", "sha256": "4" * 64},
            }],
        }]
        with (
            mock.patch(
                MODULE + "resume_project_completion", side_effect=completions,
            ),
            mock.patch(
                MODULE + "run_project_worker_preflight",
                return_value=self.preflight,
            ),
            mock.patch(
                MODULE + "dispatch_project_workers", side_effect=dispatches,
            ),
            mock.patch(
                MODULE + "run_and_ingest_opencode_worker",
                side_effect=[
                    {"status": "candidate-ready"},
                    {"status": "gate-pending"},
                ],
            ) as worker,
        ):
            result = run_project_to_completion(
                self.portfolio, **self.arguments,
            )
        self.assertEqual("completed", result["status"])
        self.assertEqual(3, len(result["cycles"]))
        self.assertEqual(2, worker.call_count)

    def test_waiting_without_dispatchable_worker_is_structured_blocker(self) -> None:
        waiting = {
            "status": "waiting", "stage": "awaiting-all-last-good",
            "checkpoint_sha256": "b" * 64,
        }
        dispatch = {
            "status": "waiting", "dispatch_sha256": "d" * 64,
            "deferred": [{"reasons": ["dependency_gate_pending"]}],
            "launches": [],
        }
        with (
            mock.patch(MODULE + "resume_project_completion", return_value=waiting),
            mock.patch(
                MODULE + "run_project_worker_preflight",
                return_value=self.preflight,
            ),
            mock.patch(MODULE + "dispatch_project_workers", return_value=dispatch),
        ):
            result = run_project_to_completion(
                self.portfolio, **self.arguments,
            )
        self.assertEqual("blocked", result["status"])
        self.assertEqual("project_run_no_progress", result["reason_code"])

    def test_attempt_limit_is_reported_as_a_stable_terminal_reason(self) -> None:
        waiting = {"status": "waiting", "stage": "candidate-worker-required"}
        dispatch = {
            "status": "blocked", "dispatch_sha256": "d" * 64,
            "deferred": [], "launches": [],
            "skipped": [{
                "worker_id": "repairer", "reason": "attempt_limit_reached",
            }],
        }
        with (
            mock.patch(MODULE + "resume_project_completion", return_value=waiting),
            mock.patch(
                MODULE + "run_project_worker_preflight",
                return_value=self.preflight,
            ),
            mock.patch(MODULE + "dispatch_project_workers", return_value=dispatch),
        ):
            result = run_project_to_completion(
                self.portfolio, **self.arguments,
            )
        self.assertEqual("blocked", result["status"])
        self.assertEqual(
            "project_worker_attempt_limit_reached", result["reason_code"],
        )


if __name__ == "__main__":
    unittest.main()
