from __future__ import annotations

import copy
import json
import unittest
from unittest import mock

from validation.tools._ai_candidate_harness_parts.provider_runtime import ProviderExecution
from validation.tools._project_migration_harness.artifacts import (
    content_sha256, write_json_artifact,
)
from validation.tools._project_migration_harness.controller import (
    dispatch_project_workers, run_and_ingest_opencode_worker,
)
from validation.tools._project_migration_harness.ledger import (
    LedgerError, LeaseConflict,
)
from validation.tools._project_migration_harness.worker_result_contracts import (
    normalize_worker_result,
)
from validation.tools.project_migration_runtime_test_support import (
    LOGICAL_MODEL,
    RESOLVED_MODEL,
    RuntimeHarnessCase,
)


class ProjectMigrationRuntimeSecurityTests(RuntimeHarnessCase):

    def test_recomputed_tampered_plan_and_active_lease_are_rejected(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        tampered = copy.deepcopy(plan["portfolio"])
        tampered["assignments"][0]["dependencies"] = ["invented-group"]
        tampered["plan_sha256"] = content_sha256({
            key: value for key, value in tampered.items() if key != "plan_sha256"
        })
        with self.assertRaises(LedgerError):
            dispatch_project_workers(
                tampered, ledger=ledger, harness_root=self.harness,
                out_root=self.out_root, out_root_rel="target/run",
            )
        launch = self.dispatch(plan, ledger)["launches"][0]
        assignment = next(
            item for item in plan["portfolio"]["assignments"]
            if item["worker_id"] == launch["worker_id"]
        )
        with self.assertRaises(LeaseConflict):
            ledger.begin_worker_attempt(
                run_id=plan["run_id"], assignment=assignment,
                ttl_seconds=900, input_sha256="a" * 64,
            )

    def test_substituted_request_is_rejected_before_model_launch(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(launch["request"])
        request["context"] = {**request["context"], "sha256": "f" * 64}
        base = {key: value for key, value in request.items() if key != "execution_binding"}
        base.pop("effective_input_sha256")
        request["effective_input_sha256"] = content_sha256(base)
        execution = dict(request["execution_binding"])
        execution["effective_input_sha256"] = request["effective_input_sha256"]
        execution["binding_sha256"] = content_sha256({
            key: value for key, value in execution.items() if key != "binding_sha256"
        })
        request["execution_binding"] = execution
        substituted = write_json_artifact(
            self.harness, "target/run/harness/substituted-request.json", request
        )
        with self.assertRaisesRegex(ValueError, "not bound"):
            run_and_ingest_opencode_worker(
                substituted, {"path": "unused", "sha256": "0" * 64},
                ledger=ledger, harness_root=self.harness,
            )
        self.assertEqual("running", ledger.running_attempt_for_worker(
            run_id=plan["run_id"], worker_id=launch["worker_id"]
        )["status"])

    def test_forged_preflight_is_prelaunch_blocked_without_consuming_attempt(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        result = run_and_ingest_opencode_worker(
            launch["request"], self.preflight(plan["run_id"], agent="c2rust-migrator"),
            ledger=ledger, harness_root=self.harness,
            logical_model=LOGICAL_MODEL, resolved_model=RESOLVED_MODEL,
        )
        self.assertEqual("prelaunch-blocked", result["status"])
        with ledger.connect() as connection:
            self.assertEqual(
                [("cancelled", "prelaunch_cancelled")],
                [tuple(row) for row in connection.execute(
                    "select status,error_key from attempts"
                )],
            )

    def test_context_receipt_tamper_is_blocked_before_model_launch(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(launch["request"])
        receipt = self.harness / request["context_materialization"]["path"]
        receipt.write_text("{}\n", encoding="utf-8")
        preflight = self.preflight(plan["run_id"])

        with mock.patch(
            "validation.tools._project_migration_harness.controller_runtime."
            "subprocess_runner_with_environment",
        ) as runner:
            result = run_and_ingest_opencode_worker(
                launch["request"], preflight,
                ledger=ledger, harness_root=self.harness,
                logical_model=LOGICAL_MODEL, resolved_model=RESOLVED_MODEL,
            )

        self.assertEqual("prelaunch-blocked", result["status"])
        self.assertFalse(result["attempt_consumed"])
        runner.assert_not_called()
        with ledger.connect() as connection:
            self.assertEqual(
                [("cancelled", "prelaunch_cancelled")],
                [tuple(row) for row in connection.execute(
                    "select status,error_key from attempts"
                )],
            )

    def test_frontier_drift_is_blocked_before_provider_process_creation(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        with ledger.connect() as connection:
            connection.execute(
                """update context_frontiers set head_sha256=?
                   where run_id=? and unit_id=?""",
                ("f" * 64, plan["run_id"], launch["unit_id"]),
            )

        with mock.patch(
            "validation.tools._project_migration_harness.controller_runtime."
            "subprocess_runner_with_environment",
        ) as runner:
            result = run_and_ingest_opencode_worker(
                launch["request"], self.preflight(plan["run_id"]),
                ledger=ledger, harness_root=self.harness,
                logical_model=LOGICAL_MODEL, resolved_model=RESOLVED_MODEL,
            )

        self.assertEqual("prelaunch-blocked", result["status"])
        self.assertFalse(result["attempt_consumed"])
        runner.assert_not_called()
        with ledger.connect() as connection:
            self.assertEqual(
                [("cancelled", False)],
                [
                    (row["status"], json.loads(row["metadata_json"])["command_started"])
                    for row in connection.execute(
                        "select status,metadata_json from attempts"
                    )
                ],
            )

    def test_provider_success_without_started_callback_is_not_ingested(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(launch["request"])
        response = self.common(request) | {
            "candidate_source": "pub fn unit() -> i32 { 1 }\n",
        }

        def runner(*_args: object, **_kwargs: object) -> ProviderExecution:
            event = {
                "type": "text", "text": json.dumps(response), "sessionID": "s1",
            }
            return ProviderExecution(
                0, json.dumps(event) + "\n", "", identity_receipt={
                    "source": "runner-contract", "session_id": "s1",
                    "provider_id": "opencode", "model_id": "deepseek-v4-flash-free",
                    "agent": "c2rust-candidate", "variant": "max",
                    "opencode_version": "test",
                },
            )

        with mock.patch(
            "validation.tools._project_migration_harness.controller_runtime."
            "subprocess_runner_with_environment",
            side_effect=runner,
        ):
            result = run_and_ingest_opencode_worker(
                launch["request"], self.preflight(plan["run_id"]),
                ledger=ledger, harness_root=self.harness,
                logical_model=LOGICAL_MODEL, resolved_model=RESOLVED_MODEL,
            )

        self.assertEqual("prelaunch-blocked", result["status"])
        self.assertFalse(result["attempt_consumed"])
        with ledger.connect() as connection:
            self.assertEqual(0, connection.execute(
                "select count(*) from artifacts where run_id=?", (plan["run_id"],),
            ).fetchone()[0])

    def test_model_candidate_metadata_claims_are_rejected(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(launch["request"])
        response = self.common(request) | {
            "candidate_source": "pub fn unit() -> i32 { 1 }\n",
            "public_symbols": ["forged"],
            "required_symbols": ["forged"],
            "unsafe_count": 0,
        }
        with self.assertRaisesRegex(ValueError, "response fields"):
            normalize_worker_result(request, response)

    def test_host_derives_candidate_metadata_from_source_only(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(launch["request"])
        response = self.common(request) | {
            "candidate_source": "pub unsafe fn unit() -> i32 { unsafe { 1 } }\n",
        }
        calls: list[list[str]] = []

        def runner(
            argv: list[str], _timeout: int, *, environment: dict[str, str],
            cwd: object, on_started: object,
        ) -> ProviderExecution:
            _ = environment, cwd
            on_started()
            calls.append(argv)
            event = {"type": "text", "text": json.dumps(response), "sessionID": "s1"}
            return ProviderExecution(0, json.dumps(event) + "\n", "", identity_receipt={
                "source": "runner-contract", "session_id": "s1", "provider_id": "opencode",
                "model_id": "deepseek-v4-flash-free", "agent": "c2rust-candidate",
                "variant": "max", "opencode_version": "test",
            })

        with mock.patch(
            "validation.tools._project_migration_harness.controller_runtime."
            "subprocess_runner_with_environment",
            side_effect=runner,
        ):
            result = run_and_ingest_opencode_worker(
                launch["request"], self.preflight(plan["run_id"]),
                ledger=ledger, harness_root=self.harness,
                logical_model=LOGICAL_MODEL, resolved_model=RESOLVED_MODEL,
            )
        self.assertEqual("recorded", result["status"])
        self.assertEqual(1, len(calls))
        row = next(
            item
            for item in ledger.completed_orchestration_rows(plan["run_id"])["artifacts"]
            if item["kind"] == "rust-candidate"
        )
        metadata = json.loads(row["metadata_json"])
        self.assertEqual(["unit"], metadata["public_symbols"])
        self.assertEqual([], metadata["required_symbols"])
        self.assertEqual(2, metadata["unsafe_count"])

if __name__ == "__main__":
    unittest.main()
