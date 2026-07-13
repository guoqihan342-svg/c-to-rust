from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools._ai_candidate_harness_parts.provider_runtime import (
    ProviderExecution,
)
from validation.tools._project_migration_harness.controller import (
    run_and_ingest_opencode_project_repair,
)
from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.project_preflight_runner import (
    run_project_worker_preflight,
)
from validation.tools.project_migration_project_repair_test_support import (
    materialized_repair_case,
)
from validation.tools.project_migration_runtime_test_support import (
    LOGICAL_MODEL,
    RESOLVED_MODEL,
)


class ProjectRepairRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-repair-runtime-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out = self.root / "target/run"
        agent_source = (
            Path(__file__).resolve().parents[2]
            / ".opencode/agents/c2rust-candidate.md"
        )
        agent_target = self.root / ".opencode/agents/c2rust-candidate.md"
        agent_target.parent.mkdir(parents=True)
        agent_target.write_bytes(agent_source.read_bytes())
        self.ledger = ProjectLedger(self.out / "state/project-migration.sqlite3")

    def test_provider_runtime_isolated_and_ingested_to_resolution(self) -> None:
        request, request_ref, _, duplicate_id = materialized_repair_case(
            self.root, self.out, self.ledger, "runtime-resolve",
        )
        response = self.response(request, [{
            "section": "public_api", "action": "remove",
            "record_id": duplicate_id, "changes": {},
        }])
        calls: list[list[str]] = []
        temporary_paths: list[Path] = []

        def runner(
            argv: list[str], _timeout: int, *,
            environment: dict[str, str], cwd: Path,
        ) -> ProviderExecution:
            calls.append(argv)
            temporary_paths.extend(Path(environment[key]) for key in (
                "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                "XDG_STATE_HOME", "TMPDIR",
            ))
            self.assertTrue(cwd.is_dir())
            self.assertTrue(all(path.is_dir() for path in temporary_paths))
            event = {
                "type": "text", "text": json.dumps(response),
                "sessionID": "session-project-repair",
            }
            return ProviderExecution(
                0, json.dumps(event) + "\n", "",
                identity_receipt={
                    "source": "runner-contract",
                    "session_id": "session-project-repair",
                    "provider_id": "opencode",
                    "model_id": "deepseek-v4-flash-free",
                    "agent": "c2rust-candidate", "variant": "max",
                    "opencode_version": "test-double",
                },
            )

        with mock.patch(
            "validation.tools._project_migration_harness.project_repair_runtime."
            "subprocess_runner_with_environment",
            side_effect=runner,
        ):
            result = run_and_ingest_opencode_project_repair(
                request_ref, self.preflight(), ledger=self.ledger,
                harness_root=self.root, out_root=self.out,
                out_root_rel="target/run", logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )

        self.assertEqual("resolved", result["status"])
        self.assertEqual(1, len(calls))
        self.assertIn("--pure", calls[0])
        self.assertIn("c2rust-candidate", calls[0])
        self.assertTrue(temporary_paths)
        self.assertTrue(all(not path.exists() for path in temporary_paths))
        expected_kinds = {
            "project-repair-context", "project-repair-request",
            "provider-prompt", "provider-raw_response",
            "provider-invocation_receipt", "provider-parsed_response",
            "provider-execution_report",
            "project-repair-response", "rust-project-ir-candidate",
            "project-interface-receipt",
        }
        artifact_kinds = self.artifact_kinds()
        self.assertTrue(
            expected_kinds.issubset(artifact_kinds),
            expected_kinds - artifact_kinds,
        )

    def test_provider_launch_failure_recovers_retryable_attempt(self) -> None:
        _, request_ref, _, _ = materialized_repair_case(
            self.root, self.out, self.ledger, "runtime-provider-failure",
        )
        with mock.patch(
            "validation.tools._project_migration_harness.project_repair_runtime."
            "subprocess_runner_with_environment",
            return_value=ProviderExecution(
                127, "", "provider_error=invocation_failed",
                process_started=False,
            ),
        ):
            result = run_and_ingest_opencode_project_repair(
                request_ref, self.preflight(), ledger=self.ledger,
                harness_root=self.root, out_root=self.out,
                out_root_rel="target/run", logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )

        self.assertEqual("retry-ready", result["status"])
        self.assertEqual("provider_invocation_failed", result["root_cause_key"])
        self.assertFalse(result["model_launched"])
        self.assertTrue({
            "provider-prompt", "provider-raw_response",
            "provider-invocation_receipt",
        }.issubset(self.artifact_kinds()))

    def test_provider_secret_output_is_redacted_before_persistence(self) -> None:
        _, request_ref, _, _ = materialized_repair_case(
            self.root, self.out, self.ledger, "runtime-secret-output",
        )
        secret_text = "api_" + "key=synthetic-value"
        event = {
            "type": "text", "text": secret_text,
            "sessionID": "session-secret-output",
        }
        with mock.patch(
            "validation.tools._project_migration_harness.project_repair_runtime."
            "subprocess_runner_with_environment",
            return_value=ProviderExecution(
                0, json.dumps(event) + "\n", "",
                identity_receipt={
                    "source": "runner-contract",
                    "session_id": "session-secret-output",
                    "provider_id": "opencode",
                    "model_id": "deepseek-v4-flash-free",
                    "agent": "c2rust-candidate", "variant": "max",
                    "opencode_version": "test-double",
                },
            ),
        ):
            result = run_and_ingest_opencode_project_repair(
                request_ref, self.preflight(), ledger=self.ledger,
                harness_root=self.root, out_root=self.out,
                out_root_rel="target/run", logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )

        self.assertEqual("retry-ready", result["status"])
        self.assertEqual("provider_secret_output", result["root_cause_key"])
        raw_ref = result["artifacts"]["raw_response"]
        persisted = (
            self.root / Path(*raw_ref["path"].split("/"))
        ).read_text(encoding="utf-8")
        self.assertNotIn(secret_text, persisted)
        self.assertIn("provider_output_redacted", persisted)

    def test_forbidden_tool_event_is_redacted_before_persistence(self) -> None:
        _, request_ref, _, _ = materialized_repair_case(
            self.root, self.out, self.ledger, "runtime-tool-output",
        )
        command = "read-hidden-project-files"
        event = {
            "type": "tool_use", "tool": "shell",
            "input": {"command": command},
        }
        with mock.patch(
            "validation.tools._project_migration_harness.project_repair_runtime."
            "subprocess_runner_with_environment",
            return_value=ProviderExecution(0, json.dumps(event) + "\n", ""),
        ):
            result = run_and_ingest_opencode_project_repair(
                request_ref, self.preflight(), ledger=self.ledger,
                harness_root=self.root, out_root=self.out,
                out_root_rel="target/run", logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )

        self.assertEqual("retry-ready", result["status"])
        self.assertEqual("provider_forbidden_tool_event", result["root_cause_key"])
        raw_ref = result["artifacts"]["raw_response"]
        persisted = (
            self.root / Path(*raw_ref["path"].split("/"))
        ).read_text(encoding="utf-8")
        self.assertNotIn(command, persisted)
        self.assertNotIn('"tool":"shell"', persisted)
        self.assertIn("provider_output_redacted", persisted)

    def test_started_command_with_unknown_result_requires_manual_reconciliation(self) -> None:
        request, request_ref, _, _ = materialized_repair_case(
            self.root, self.out, self.ledger, "runtime-unknown-result",
        )

        def runner(
            _argv: list[str], _timeout: int, *,
            environment: dict[str, str], cwd: Path,
        ) -> ProviderExecution:
            self.assertTrue(environment)
            self.assertTrue(cwd.is_dir())
            raise RuntimeError("synthetic lost provider result")

        with mock.patch(
            "validation.tools._project_migration_harness.project_repair_runtime."
            "subprocess_runner_with_environment",
            side_effect=runner,
        ):
            result = run_and_ingest_opencode_project_repair(
                request_ref, self.preflight(), ledger=self.ledger,
                harness_root=self.root, out_root=self.out,
                out_root_rel="target/run", logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )

        self.assertEqual("manual-reconcile", result["status"])
        self.assertEqual("failed", result["current_state"])
        projection = self.ledger.project_repair_projection(
            run_id="run",
            queue_sha256=request["project_repair_queue_sha256"],
            repair_id=request["repair_id"],
        )
        self.assertEqual("failed", projection.status)
        with self.ledger.connect() as connection:
            attempt = connection.execute(
                """select status,command_started,error_key
                   from project_repair_attempts where attempt_id=?""",
                (request["execution_binding"]["attempt_id"],),
            ).fetchone()
        self.assertEqual(("failed", 1, "project_repair_provider_result_unknown"), tuple(attempt))

    def preflight(self) -> dict:
        with mock.patch(
            "validation.tools._project_migration_harness.project_preflight_runner."
            "subprocess_runner_with_environment",
            return_value=ProviderExecution(0, f"{RESOLVED_MODEL}\n", ""),
        ):
            generated = run_project_worker_preflight(
                harness_root=self.root, out_root_rel="target/preflight",
                run_id="run", logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )
        return generated["report"]

    def artifact_kinds(self) -> set[str]:
        with self.ledger.connect() as connection:
            rows = connection.execute(
                "select kind from project_repair_artifacts where run_id=?",
                ("run",),
            ).fetchall()
        return {str(row["kind"]) for row in rows}

    @staticmethod
    def response(request: dict, operations: list[dict]) -> dict:
        return {
            "schema_version": 1, "run_id": request["run_id"],
            "role": "project-repairer",
            "project_repair_queue_sha256": request["project_repair_queue_sha256"],
            "repair_id": request["repair_id"],
            "attempt_id": request["execution_binding"]["attempt_id"],
            "effective_input_sha256": request["effective_input_sha256"],
            "base_rust_project_ir_sha256": request[
                "base_rust_project_ir"
            ]["ir_sha256"],
            "context_sha256": request["project_repair_context"]["context_sha256"],
            "operations": operations,
        }


if __name__ == "__main__":
    unittest.main()
