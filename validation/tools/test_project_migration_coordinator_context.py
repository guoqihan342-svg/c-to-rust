from __future__ import annotations

import json
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.project_interface_model_context import (
    build_model_coordinator_context,
    validate_model_coordinator_context,
)
from validation.tools._project_migration_harness.project_interface_contract import (
    coordinator_receipt_accepts_repair_candidate,
)
from validation.tools._project_migration_harness.project_prompt import (
    render_project_worker_prompt,
)
from validation.tools._project_migration_harness.runtime_request_validation import (
    bound_worker_request,
)
from validation.tools.project_migration_project_repair_test_support import (
    coordinated_case,
)
from validation.tools.project_migration_runtime_test_support import RuntimeHarnessCase


class CoordinatorContextTests(RuntimeHarnessCase):
    def test_candidate_cannot_swap_old_diagnostics_for_new_ones(self) -> None:
        _, previous = coordinated_case("two-conflicts", additional_conflict=True)
        _, replacement = coordinated_case("replacement-conflict")
        target = previous["diagnostics"][0]["diagnostic_sha256"]

        self.assertFalse(coordinator_receipt_accepts_repair_candidate(
            previous, replacement, diagnostic_sha256=target,
        ))

    def test_subject_projection_is_bounded_content_addressed_and_fail_closed(self) -> None:
        _, receipt = coordinated_case("context")
        relevant = build_model_coordinator_context(
            receipt, receipt_epoch=4, subject_unit_ids=["unit-a"],
        )
        irrelevant = build_model_coordinator_context(
            receipt, receipt_epoch=4, subject_unit_ids=["unrelated-unit"],
        )

        self.assertEqual(1, relevant["visible_diagnostic_count"])
        self.assertEqual(0, irrelevant["visible_diagnostic_count"])
        self.assertEqual(
            relevant["coordinator_receipt_sha256"],
            irrelevant["coordinator_receipt_sha256"],
        )
        self.assertNotEqual(relevant["context_sha256"], irrelevant["context_sha256"])
        drifted = json.loads(json.dumps(relevant))
        drifted["diagnostics"][0]["code"] = "masked_conflict"
        with self.assertRaisesRegex(ValueError, "SHA drifted"):
            validate_model_coordinator_context(drifted)

    def test_latest_receipt_epoch_reaches_worker_request_and_prompt(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        unit_id = plan["portfolio"]["assignments"][0]["unit_id"]
        dag_sha256 = self.run_ir_dag_binding_sha(ledger, plan["run_id"])
        first_ir, first = coordinated_case(
            "first", unit_id=unit_id, dag_sha256=dag_sha256,
        )
        second_ir, second = coordinated_case(
            "second", unit_id=unit_id, dag_sha256=dag_sha256,
        )
        first_registration = ledger.register_project_interface_receipt(
            run_id=plan["run_id"], receipt=first, rust_project_ir=first_ir,
        )
        second_registration = ledger.register_project_interface_receipt(
            run_id=plan["run_id"], receipt=second, rust_project_ir=second_ir,
        )

        launch = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(launch["request"])
        context = request["input_facts"]["coordinator_context"]
        prompt = json.loads(render_project_worker_prompt(
            request, harness_root=self.harness,
        ))

        self.assertEqual(1, first_registration.receipt_epoch)
        self.assertEqual(2, second_registration.receipt_epoch)
        self.assertEqual(2, context["receipt_epoch"])
        self.assertEqual(
            second_registration.coordinator_receipt_sha256,
            context["coordinator_receipt_sha256"],
        )
        self.assertEqual([unit_id], context["subject_unit_ids"])
        self.assertEqual(context, prompt["bound_inputs"]["coordinator_context"])
        self.assertNotIn("bindings", json.dumps(context, sort_keys=True))
        self.assertNotIn("source", json.dumps(context, sort_keys=True))

    def test_context_for_another_unit_cannot_be_rebound_by_rehashing_request(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        unit_id = plan["portfolio"]["assignments"][0]["unit_id"]
        rust_project_ir, receipt = coordinated_case(
            "swap", unit_id=unit_id,
            dag_sha256=self.run_ir_dag_binding_sha(ledger, plan["run_id"]),
        )
        registration = ledger.register_project_interface_receipt(
            run_id=plan["run_id"], receipt=receipt,
            rust_project_ir=rust_project_ir,
        )
        launch = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(launch["request"])
        request["input_facts"]["coordinator_context"] = (
            build_model_coordinator_context(
                receipt, receipt_epoch=registration.receipt_epoch,
                subject_unit_ids=["another-unit"],
            )
        )
        payload = {
            key: value for key, value in request.items()
            if key not in {"effective_input_sha256", "execution_binding"}
        }
        request["effective_input_sha256"] = content_sha256(payload)

        with self.assertRaisesRegex(ValueError, "not bound to this worker group"):
            render_project_worker_prompt(request, harness_root=self.harness)

    def test_already_dispatched_worker_rejects_a_stale_receipt_epoch(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        unit_id = plan["portfolio"]["assignments"][0]["unit_id"]
        dag_sha256 = self.run_ir_dag_binding_sha(ledger, plan["run_id"])
        first_ir, first = coordinated_case(
            "runtime-first", unit_id=unit_id, dag_sha256=dag_sha256,
        )
        ledger.register_project_interface_receipt(
            run_id=plan["run_id"], receipt=first, rust_project_ir=first_ir,
        )
        launch = self.dispatch(plan, ledger)["launches"][0]
        second_ir, second = coordinated_case(
            "runtime-second", unit_id=unit_id, dag_sha256=dag_sha256,
        )
        ledger.register_project_interface_receipt(
            run_id=plan["run_id"], receipt=second, rust_project_ir=second_ir,
        )

        with self.assertRaisesRegex(ValueError, "coordinator context is stale"):
            bound_worker_request(
                launch["request"], ledger=ledger, harness_root=self.harness,
            )

    def test_worker_dispatched_before_first_receipt_must_be_replanned(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        unit_id = plan["portfolio"]["assignments"][0]["unit_id"]
        rust_project_ir, receipt = coordinated_case(
            "runtime-late-first", unit_id=unit_id,
            dag_sha256=self.run_ir_dag_binding_sha(ledger, plan["run_id"]),
        )
        ledger.register_project_interface_receipt(
            run_id=plan["run_id"], receipt=receipt,
            rust_project_ir=rust_project_ir,
        )

        with self.assertRaisesRegex(ValueError, "missing the latest receipt"):
            bound_worker_request(
                launch["request"], ledger=ledger, harness_root=self.harness,
            )

    @staticmethod
    def run_ir_dag_binding_sha(ledger, run_id: str) -> str:
        with ledger.connect() as connection:
            row = connection.execute(
                "select metadata_json from project_runs where run_id=?", (run_id,),
            ).fetchone()
        metadata = json.loads(str(row[0]))
        return str(
            metadata["migration_contract"]["integration_manifest"]["sha256"]
        )


if __name__ == "__main__":
    unittest.main()
