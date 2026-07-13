from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest import mock

from validation.tools._ai_candidate_harness_parts.provider_runtime import ProviderExecution
from validation.tools._project_migration_harness.controller import (
    ingest_worker_result,
    run_and_ingest_opencode_worker,
)
from validation.tools._project_migration_harness.controller_gates import (
    record_candidate_gate,
)
from validation.tools._project_migration_harness.project_prompt import (
    render_project_worker_prompt,
)
from validation.tools.project_migration_runtime_test_support import (
    LOGICAL_MODEL,
    RESOLVED_MODEL,
    RuntimeHarnessCase,
)


class ProjectMigrationRuntimeFailClosedTests(RuntimeHarnessCase):
    def test_process_creation_failure_does_not_consume_attempt(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        execution = ProviderExecution(
            127,
            "",
            "provider_error=invocation_failed",
            process_started=False,
        )
        with mock.patch(
            "validation.tools._project_migration_harness.controller_runtime."
            "subprocess_runner_with_environment",
            return_value=execution,
        ):
            result = run_and_ingest_opencode_worker(
                launch["request"],
                self.preflight(plan["run_id"]),
                ledger=ledger,
                harness_root=self.harness,
                logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )
        self.assertEqual("prelaunch-blocked", result["status"])
        self.assertFalse(result["attempt_consumed"])
        self.assertFalse(result["model_launched"])
        with ledger.connect() as connection:
            self.assertEqual(0, connection.execute("select count(*) from attempts").fetchone()[0])

    def test_tool_event_after_command_is_manual_and_never_retried(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        calls = 0

        def runner(
            _argv: list[str], _timeout: int, *, environment: dict[str, str],
            cwd: object, on_started: object,
        ) -> ProviderExecution:
            nonlocal calls
            _ = environment, cwd
            on_started()
            calls += 1
            return ProviderExecution(0, '{"type":"tool-call","tool":"shell"}\n', "")

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
        self.assertEqual("manual-reconcile", result["status"])
        self.assertEqual(1, calls)
        self.assertEqual(
            "terminal",
            ledger.unit_states(plan["run_id"])[0]["resumable_status"],
        )

    def test_repair_dispatch_projects_bound_candidate_gate_verdict(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        translator = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(translator["request"])
        candidate = ingest_worker_result(
            self.common(request) | {
                "candidate_source": "pub fn unit() -> i32 { 2 }\n"
            },
            ledger=ledger,
            harness_root=self.harness,
            run_id=plan["run_id"],
            worker_id=translator["worker_id"],
        )
        record_candidate_gate(
            ledger=ledger,
            out_root=self.out_root,
            out_root_rel="target/run",
            run_id=plan["run_id"],
            unit_id=translator["unit_id"],
            candidate_artifact_id=candidate["artifact_id"],
            record_id="failed-compile",
            kind="verifier",
            gate_family="compile",
            status="failed",
            verifier_id="ignored-by-host",
            diagnostics=[{
                "code": "rustc-type-error",
                "stage": "compile",
                "message": "type mismatch",
            }],
        )
        repair = self.dispatch(plan, ledger)["launches"][0]
        repair_request = self.load(repair["request"])
        prompt = json.loads(render_project_worker_prompt(
            repair_request,
            harness_root=self.harness,
        ))
        projected = prompt["bound_inputs"]["failed_gate_result"]
        self.assertEqual("model-safe-gate-evidence", projected["artifact_kind"])
        self.assertEqual(candidate["artifact_id"], projected["candidate_artifact_id"])
        self.assertEqual(
            repair_request["input_facts"]["candidate_artifact_sha256"],
            projected["candidate_artifact_sha256"],
        )

    def test_boundary_preserve_continues_with_host_manifest(self) -> None:
        plan = self.plan(
            "#define PICK(x) ((x) + 1)\nint unit(void) { return PICK(1); }\n"
        )
        ledger = self.ledger()
        planner = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(planner["request"])
        ingest_worker_result(
            self.common(request) | {
                "decision": "preserve_ffi_boundary",
                "boundary_reason": "macro boundary",
            },
            ledger=ledger,
            harness_root=self.harness,
            run_id=plan["run_id"],
            worker_id=planner["worker_id"],
        )
        translator = self.dispatch(plan, ledger)["launches"][0]
        candidate_request = self.load(translator["request"])
        result = ingest_worker_result(
            self.common(candidate_request) | {
                "candidate_source": (
                    '#[no_mangle]\npub extern "C" fn unit() -> i32 { 1 }\n'
                ),
            },
            ledger=ledger,
            harness_root=self.harness,
            run_id=plan["run_id"],
            worker_id=translator["worker_id"],
        )
        self.assertEqual("recorded", result["status"])
        artifact = ledger.completed_orchestration_rows(plan["run_id"])["artifacts"][-1]
        manifest = json.loads(artifact["metadata_json"])["boundary_manifest"]
        self.assertTrue(
            (self.harness / Path(*manifest["path"].split("/"))).is_file()
        )

    def test_boundary_refusal_fails_run_instead_of_hanging_active(self) -> None:
        plan = self.plan(
            "#define PICK(x) ((x) + 1)\nint unit(void) { return PICK(1); }\n"
        )
        ledger = self.ledger()
        planner = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(planner["request"])
        result = ingest_worker_result(
            self.common(request) | {
                "decision": "refuse_with_reason",
                "refusal_reason": "unsupported contract",
            },
            ledger=ledger,
            harness_root=self.harness,
            run_id=plan["run_id"],
            worker_id=planner["worker_id"],
        )
        self.assertTrue(result["terminal"])
        state = ledger.unit_states(plan["run_id"])[0]
        self.assertEqual(
            ("failed", "terminal", "failed"),
            (state["status"], state["resumable_status"], state["run_status"]),
        )


if __name__ == "__main__":
    unittest.main()
