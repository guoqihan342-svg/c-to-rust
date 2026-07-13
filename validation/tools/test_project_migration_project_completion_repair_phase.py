from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from validation.tools._project_migration_harness.project_completion_repair_phase import (
    execute_project_repair_completion_step,
)


class ProjectCompletionRepairPhaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.initial = {
            "schema_version": 1, "status": "preflight-required",
            "stage": "project-interface-repair",
            "project_repair": {
                "status": "preflight-required", "blockers": [],
            },
        }
        self.preflight = {
            "schema_version": 1, "status": "passed",
            "report": {"path": "target/run/preflight/report.json", "sha256": "a" * 64},
            "provider_invocations": 0, "model_launched": False,
        }
        self.dispatched = {
            "schema_version": 1, "status": "repair-dispatched",
            "stage": "project-interface-repair",
            "project_repair": {
                "status": "repair-dispatched",
                "request": {"path": "target/run/request.json", "sha256": "b" * 64},
                "blockers": [],
            },
        }

    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.run_and_ingest_opencode_project_repair"
    )
    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.integrate_verified_project_repair"
    )
    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.issue_project_repair_dispatch_permit",
        return_value=mock.sentinel.dispatch_permit,
    )
    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.run_project_worker_preflight"
    )
    def test_one_resume_executes_at_most_one_provider_call(
        self, preflight: mock.Mock, _issue: mock.Mock, integrate: mock.Mock,
        runtime: mock.Mock,
    ) -> None:
        preflight.return_value = self.preflight
        integrate.return_value = self.dispatched
        runtime.return_value = {
            "schema_version": 1, "status": "resolved",
            "generation": {"provider_invocations": 1, "model_launched": True},
        }
        result = self.execute()
        self.assertEqual(("waiting", 1, True), (
            result["status"], result["provider_invocations"],
            result["model_launched"],
        ))
        preflight.assert_called_once()
        integrate.assert_called_once()
        runtime.assert_called_once()
        self.assertIs(
            mock.sentinel.dispatch_permit,
            integrate.call_args.kwargs["repair_dispatch_permit"],
        )

    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.run_and_ingest_opencode_project_repair"
    )
    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.integrate_verified_project_repair"
    )
    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.issue_project_repair_dispatch_permit",
        return_value=mock.sentinel.dispatch_permit,
    )
    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.run_project_worker_preflight"
    )
    def test_failed_preflight_does_not_dispatch_or_consume_an_attempt(
        self, preflight: mock.Mock, issue: mock.Mock, integrate: mock.Mock,
        runtime: mock.Mock,
    ) -> None:
        preflight.return_value = {**self.preflight, "status": "blocked"}
        result = self.execute()
        self.assertEqual("blocked", result["status"])
        self.assertEqual(0, result["provider_invocations"])
        integrate.assert_not_called()
        issue.assert_not_called()
        runtime.assert_not_called()

    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.run_and_ingest_opencode_project_repair"
    )
    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.integrate_verified_project_repair"
    )
    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.issue_project_repair_dispatch_permit",
        return_value=mock.sentinel.dispatch_permit,
    )
    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.run_project_worker_preflight"
    )
    def test_dispatch_race_is_observed_without_a_second_launch(
        self, preflight: mock.Mock, _issue: mock.Mock, integrate: mock.Mock,
        runtime: mock.Mock,
    ) -> None:
        preflight.return_value = self.preflight
        integrate.return_value = {
            "schema_version": 1, "status": "waiting",
            "stage": "project-interface-repair",
            "project_repair": {
                "status": "waiting", "stage": "project-repair-attempt-active",
                "blockers": [],
            },
        }
        result = self.execute()
        self.assertEqual("waiting", result["status"])
        self.assertEqual(0, result["provider_invocations"])
        runtime.assert_not_called()

    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.run_project_worker_preflight"
    )
    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.ingest_recorded_project_repair_result"
    )
    def test_recorded_result_resumes_ingest_without_preflight_or_model(
        self, ingest: mock.Mock, preflight: mock.Mock,
    ) -> None:
        ingest.return_value = {
            "schema_version": 1, "status": "resolved",
            "provider_invocations": 0, "model_launched": False,
        }
        self.initial["project_repair"] = {
            "status": "ingest-required",
            "request": {"path": "target/run/request.json", "sha256": "a" * 64},
            "response": {"path": "target/run/response.json", "sha256": "b" * 64},
        }
        result = self.execute()
        self.assertEqual(("waiting", 0, False), (
            result["status"], result["provider_invocations"],
            result["model_launched"],
        ))
        ingest.assert_called_once()
        preflight.assert_not_called()

    def test_recorded_result_waits_for_ingest_instead_of_blocking(self) -> None:
        result = self.runtime_result("ingest-required")
        self.assertEqual((
            "waiting", "project-repair-provider-result-recorded", [],
        ), (result["status"], result["stage"], result["blockers"]))

    def test_terminal_runtime_replay_observes_advanced_state(self) -> None:
        result = self.runtime_result("terminal-replay")
        self.assertEqual((
            "waiting", "project-repair-state-advanced", [],
        ), (result["status"], result["stage"], result["blockers"]))

    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.run_and_ingest_opencode_project_repair"
    )
    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.integrate_verified_project_repair"
    )
    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.issue_project_repair_dispatch_permit",
        return_value=mock.sentinel.dispatch_permit,
    )
    @mock.patch(
        "validation.tools._project_migration_harness."
        "project_completion_repair_phase.run_project_worker_preflight"
    )
    def runtime_result(
        self, status: str, preflight: mock.Mock, _issue: mock.Mock,
        integrate: mock.Mock, runtime: mock.Mock,
    ) -> dict:
        preflight.return_value = self.preflight
        integrate.return_value = self.dispatched
        runtime.return_value = {
            "schema_version": 1, "status": status,
            "provider_invocations": 0, "model_launched": False,
        }
        return self.execute()

    def execute(self) -> dict:
        return execute_project_repair_completion_step(
            {}, initial_integration=self.initial, ledger=mock.Mock(),
            run_id="run", harness_root=Path("."), out_root=Path("target/run"),
            out_root_rel="target/run", project_root=Path("target/run/project"),
            logical_model="GLM-5.1", resolved_model="zai/glm-5.1",
            timeout_seconds=300, preflight_timeout_seconds=60,
        )


if __name__ == "__main__":
    unittest.main()
