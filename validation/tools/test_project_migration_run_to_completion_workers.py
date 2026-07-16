from __future__ import annotations

from contextlib import ExitStack, contextmanager
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from validation.tools._project_migration_harness.project_run_to_completion import (
    run_project_to_completion,
)


MODULE = (
    "validation.tools._project_migration_harness."
    "project_run_to_completion."
)


class ProjectRunToCompletionWorkerBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-worker-batch-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out_root = self.root / "target" / "run"
        self.out_root.mkdir(parents=True)
        self.ledger = mock.Mock()
        self.arguments = {
            "ledger": self.ledger, "harness_root": self.root,
            "repo_root": self.root, "out_root": self.out_root,
            "out_root_rel": "target/run", "max_cycles": 8,
        }
        self.portfolio = {"run_id": "run"}
        self.preflight = {
            "status": "passed",
            "report": {"path": "target/run/preflight.json", "sha256": "a" * 64},
        }

    def test_dispatched_workers_really_execute_concurrently(self) -> None:
        barrier = threading.Barrier(2)

        def worker(*_args, **_kwargs):
            barrier.wait(timeout=2)
            return {"status": "recorded"}

        with self.patches(
            completions=[self.waiting(), self.completed()],
            dispatches=[self.dispatch("a", "b")], worker=worker,
        ) as calls:
            result = run_project_to_completion(self.portfolio, **self.arguments)

        self.assertEqual("completed", result["status"])
        self.assertEqual(2, calls.call_count)
        self.assertEqual(2, len(result["cycles"][0]["workers"]))

    def test_terminal_worker_does_not_leave_sibling_batch_unexecuted(self) -> None:
        visited = []

        def worker(request, *_args, **_kwargs):
            visited.append(request["path"])
            return {
                "status": "manual-reconcile" if request["path"].endswith("a.json")
                else "recorded",
            }

        with self.patches(
            completions=[self.waiting()],
            dispatches=[self.dispatch("a", "b")], worker=worker,
        ):
            result = run_project_to_completion(self.portfolio, **self.arguments)

        self.assertEqual("manual-reconcile", result["status"])
        self.assertCountEqual([
            "target/run/a.json", "target/run/b.json",
        ], visited)
        self.assertEqual(2, len(result["cycles"][0]["workers"]))

    def test_safe_prelaunch_failure_retries_and_then_completes(self) -> None:
        responses = iter([
            {"status": "prelaunch-blocked", "attempt_consumed": False},
            {"status": "recorded"},
        ])
        with self.patches(
            completions=[self.waiting(), self.waiting(), self.completed()],
            dispatches=[self.dispatch("a"), self.dispatch("b")],
            worker=lambda *_args, **_kwargs: next(responses),
        ):
            result = run_project_to_completion(self.portfolio, **self.arguments)

        self.assertEqual("completed", result["status"])
        self.assertEqual("prelaunch-blocked", result["cycles"][0]["workers"][0]["status"])
        self.assertEqual(3, len(result["cycles"]))

    def test_repeated_prelaunch_no_progress_stops_after_two_batches(self) -> None:
        with self.patches(
            completions=[self.waiting(), self.waiting()],
            dispatches=[self.dispatch("a"), self.dispatch("b")],
            worker=lambda *_args, **_kwargs: {
                "status": "prelaunch-blocked", "attempt_consumed": False,
            },
        ) as calls:
            result = run_project_to_completion(self.portfolio, **self.arguments)

        self.assertEqual("blocked", result["status"])
        self.assertEqual(
            "project_worker_prelaunch_retry_exhausted", result["reason_code"],
        )
        self.assertEqual(2, calls.call_count)

    @contextmanager
    def patches(self, *, completions, dispatches, worker):
        with ExitStack() as stack:
            stack.enter_context(mock.patch(
                MODULE + "resume_project_completion", side_effect=completions,
            ))
            stack.enter_context(mock.patch(
                MODULE + "run_project_worker_preflight", return_value=self.preflight,
            ))
            stack.enter_context(mock.patch(
                MODULE + "dispatch_project_workers", side_effect=dispatches,
            ))
            yield stack.enter_context(mock.patch(
                MODULE + "run_and_ingest_opencode_worker", side_effect=worker,
            ))

    @staticmethod
    def waiting() -> dict:
        return {"status": "waiting", "stage": "candidate-worker-required"}

    @staticmethod
    def completed() -> dict:
        return {"status": "completed", "semantic_gate": True}

    @staticmethod
    def dispatch(*names: str) -> dict:
        return {
            "status": "dispatched", "dispatch_sha256": "d" * 64,
            "deferred": [], "launches": [{
                "worker_id": f"worker-{name}", "unit_id": f"unit-{name}",
                "attempt_id": f"attempt-{name}", "fencing_token": 1,
                "request": {
                    "path": f"target/run/{name}.json", "sha256": "e" * 64,
                },
            } for name in names],
        }


if __name__ == "__main__":
    unittest.main()
