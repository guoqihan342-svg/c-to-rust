from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest import mock

from validation.tools._ai_candidate_harness_parts.provider_runtime import ProviderExecution
from validation.tools._project_migration_harness.controller import (
    run_and_ingest_opencode_worker,
)
from validation.tools._project_migration_harness.execution_evidence import (
    validate_provider_execution_evidence,
)
from validation.tools.project_migration_runtime_test_support import (
    LOGICAL_MODEL,
    RESOLVED_MODEL,
    RuntimeHarnessCase,
)


class ProjectMigrationOpenCodeRuntimeTests(RuntimeHarnessCase):
    def test_auxiliary_model_uses_preflight_tool_free_json_and_records_candidate(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(launch["request"])
        response = self.common(request) | {
            "candidate_source": "pub fn unit() -> i32 { 1 }\n",
        }
        calls: list[list[str]] = []

        def runner(
            argv: list[str], _timeout: int, *, environment: dict[str, str],
            cwd: Path, on_started: object,
        ) -> ProviderExecution:
            _ = environment, cwd
            on_started()
            calls.append(argv)
            event = {
                "type": "text",
                "text": json.dumps(response),
                "sessionID": "session-aux-1",
            }
            return ProviderExecution(
                0,
                json.dumps(event) + "\n",
                "",
                identity_receipt={
                    "source": "runner-contract",
                    "session_id": "session-aux-1",
                    "provider_id": "opencode",
                    "model_id": "deepseek-v4-flash-free",
                    "agent": "c2rust-candidate",
                    "variant": "max",
                    "opencode_version": "test-double",
                },
            )

        with mock.patch(
            "validation.tools._project_migration_harness.controller_runtime."
            "subprocess_runner_with_environment",
            side_effect=runner,
        ):
            result = run_and_ingest_opencode_worker(
                launch["request"],
                self.preflight(plan["run_id"]),
                ledger=ledger,
                harness_root=self.harness,
                logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )

        self.assertEqual("recorded", result["status"])
        self.assertEqual(1, len(calls))
        argv = calls[0]
        self.assertIn("--pure", argv)
        self.assertIn("c2rust-candidate", argv)
        self.assertNotIn("c2rust-migrator", argv)
        self.assertEqual(
            "auxiliary-local-validation",
            result["generation"]["preflight"]["proof_scope"],
        )
        artifacts = ledger.orchestration_rows(plan["run_id"])["artifacts"]
        self.assertEqual(
            ["provider-execution", "rust-candidate"],
            [item["kind"] for item in artifacts],
        )
        execution, candidate = artifacts
        validate_provider_execution_evidence(
            ledger.path,
            execution,
            run_id=plan["run_id"],
            unit_id=str(candidate["unit_id"]),
            attempt_id=str(candidate["attempt_id"]),
            worker_id=str(candidate["worker_id"]),
            fencing_token=int(candidate["fencing_token"]),
            role="translator",
        )
        receipt_ref = result["generation"]["artifacts"]["invocation_receipt"]
        receipt_path = self.harness / Path(*receipt_ref["path"].split("/"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["raw_response_sha256"] = "0" * 64
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "SHA-256 drifted|receipt contract"):
            validate_provider_execution_evidence(
                ledger.path,
                execution,
                run_id=plan["run_id"],
                unit_id=str(candidate["unit_id"]),
                attempt_id=str(candidate["attempt_id"]),
                worker_id=str(candidate["worker_id"]),
                fencing_token=int(candidate["fencing_token"]),
                role="translator",
            )
        self.assertFalse(result["semantic_gate"])

    def test_production_worker_runner_receives_attempt_isolated_environment(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(launch["request"])
        response = self.common(request) | {
            "candidate_source": "pub fn unit() -> i32 { 1 }\n",
        }
        captured_paths: list[Path] = []
        captured: dict[str, object] = {}

        def process(
            argv: list[str], _timeout: int, *,
            environment: dict[str, str], cwd: Path, on_started: object,
        ) -> ProviderExecution:
            on_started()
            captured["cwd"] = cwd
            captured["argv"] = argv
            captured_paths.extend(Path(environment[key]) for key in (
                "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                "XDG_STATE_HOME", "TMPDIR",
            ))
            captured["paths_exist"] = all(path.is_dir() for path in captured_paths)
            event = {
                "type": "text",
                "text": json.dumps(response),
                "sessionID": "session-isolated-worker",
            }
            return ProviderExecution(
                0,
                json.dumps(event) + "\n",
                "",
                identity_receipt={
                    "source": "runner-contract",
                    "session_id": "session-isolated-worker",
                    "provider_id": "opencode",
                    "model_id": "deepseek-v4-flash-free",
                    "agent": "c2rust-candidate",
                    "variant": "max",
                    "opencode_version": "test-double",
                },
            )

        with mock.patch(
            "validation.tools._project_migration_harness.controller_runtime."
            "subprocess_runner_with_environment",
            side_effect=process,
        ):
            result = run_and_ingest_opencode_worker(
                launch["request"],
                self.preflight(plan["run_id"]),
                ledger=ledger,
                harness_root=self.harness,
                logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )
        self.assertEqual("recorded", result["status"])
        self.assertNotEqual(self.harness, captured["cwd"])
        self.assertFalse(Path(captured["cwd"]).exists())
        self.assertIn("--pure", captured["argv"])
        self.assertTrue(captured["paths_exist"])
        self.assertTrue(captured_paths)
        self.assertTrue(all(not path.exists() for path in captured_paths))
        environment = result["generation"]["runtime_environment"]
        self.assertEqual("isolated", environment["status"])
        self.assertFalse(environment["global_environment_mutated"])


if __name__ == "__main__":
    unittest.main()
