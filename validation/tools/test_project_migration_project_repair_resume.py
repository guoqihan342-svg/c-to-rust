from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools._ai_candidate_harness_parts.provider_runtime import (
    ProviderExecution,
)
from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.project_repair_coordinator import (
    resume_latest_project_repair,
)
from validation.tools._project_migration_harness.project_repair_result_recovery import (
    ingest_recorded_project_repair_result,
)
from validation.tools._project_migration_harness.project_repair_runtime import (
    run_and_ingest_opencode_project_repair,
)
from validation.tools.project_migration_project_repair_test_support import (
    materialized_repair_case,
)
from validation.tools.project_migration_runtime_test_support import (
    LOGICAL_MODEL, RESOLVED_MODEL,
)


class ProjectRepairResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-repair-resume-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out = self.root / "target/run"
        self.ledger = ProjectLedger(self.out / "state/project-migration.sqlite3")

    def test_recorded_provider_result_resumes_ingest_without_second_launch(self) -> None:
        request, request_ref, _, duplicate_id = materialized_repair_case(
            self.root, self.out, self.ledger, "recorded-result-resume",
        )
        response = {
            "schema_version": 1, "run_id": request["run_id"],
            "role": "project-repairer",
            "project_repair_queue_sha256": request["project_repair_queue_sha256"],
            "repair_id": request["repair_id"],
            "attempt_id": request["execution_binding"]["attempt_id"],
            "effective_input_sha256": request["effective_input_sha256"],
            "base_rust_project_ir_sha256": request["base_rust_project_ir"]["ir_sha256"],
            "context_sha256": request["project_repair_context"]["context_sha256"],
            "operations": [{
                "section": "public_api", "action": "remove",
                "record_id": duplicate_id, "changes": {},
            }],
        }
        event = {
            "type": "text", "text": json.dumps(response),
            "sessionID": "session-recorded-result",
        }
        execution = ProviderExecution(
            0, json.dumps(event) + "\n", "",
            identity_receipt={
                "source": "runner-contract",
                "session_id": "session-recorded-result",
                "provider_id": "opencode",
                "model_id": "deepseek-v4-flash-free",
                "agent": "c2rust-candidate", "variant": "max",
                "opencode_version": "test-double",
            },
        )
        preflight_ref = request["preflight_binding"]["preflight"]
        with (
            mock.patch(
                "validation.tools._project_migration_harness.project_repair_runtime."
                "subprocess_runner_with_environment", return_value=execution,
            ) as provider,
            mock.patch(
                "validation.tools._project_migration_harness.project_repair_runtime."
                "ingest_project_repair_response",
                side_effect=RuntimeError("synthetic ingest crash"),
            ),
        ):
            interrupted = run_and_ingest_opencode_project_repair(
                request_ref, preflight_ref, ledger=self.ledger,
                harness_root=self.root, out_root=self.out,
                out_root_rel="target/run", logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )
        self.assertEqual("ingest-required", interrupted["status"])
        provider.assert_called_once()

        action = resume_latest_project_repair(
            ledger=self.ledger, run_id="run",
            base_rust_project_ir=request["base_rust_project_ir"],
            harness_root=self.root, out_root=self.out,
            out_root_rel="target/run",
        )
        self.assertEqual("ingest-required", action["status"])
        with self.ledger.connect() as connection:
            execution_report = connection.execute(
                """select repo_rel_path from project_repair_artifacts
                   where attempt_id=? and kind='provider-execution_report'""",
                (request["execution_binding"]["attempt_id"],),
            ).fetchone()
        report_path = self.root / execution_report["repo_rel_path"]
        original_report = report_path.read_bytes()
        report_path.write_bytes(original_report + b"\n")
        with self.assertRaisesRegex(
            LedgerError, "recorded project repair result artifact drifted",
        ):
            ingest_recorded_project_repair_result(
                action["request"], action["response"], ledger=self.ledger,
                harness_root=self.root, out_root=self.out,
                out_root_rel="target/run",
            )
        report_path.write_bytes(original_report)
        recovered = ingest_recorded_project_repair_result(
            action["request"], action["response"], ledger=self.ledger,
            harness_root=self.root, out_root=self.out,
            out_root_rel="target/run",
        )
        self.assertEqual("resolved", recovered["status"])
        self.assertEqual(0, recovered["provider_invocations"])

        with mock.patch(
            "validation.tools._project_migration_harness.project_repair_runtime."
            "subprocess_runner_with_environment",
        ) as duplicate_provider:
            replay = run_and_ingest_opencode_project_repair(
                request_ref, preflight_ref, ledger=self.ledger,
                harness_root=self.root, out_root=self.out,
                out_root_rel="target/run", logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )
        self.assertEqual("terminal-replay", replay["status"])
        self.assertEqual("resolved", replay["item_status"])
        duplicate_provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()
