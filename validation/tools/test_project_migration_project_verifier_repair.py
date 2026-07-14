from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.ledger import LedgerError
from validation.tools._project_migration_harness.project_interface_contract import (
    validate_coordinator_receipt,
)
from validation.tools._project_migration_harness.project_interface_coordinator import (
    coordinate_project_interfaces,
)
from validation.tools._project_migration_harness.project_repair_context import (
    build_project_repair_context, validate_project_repair_context,
)
from validation.tools._project_migration_harness.project_completion_invariants import (
    require_project_interface_ready,
)
from validation.tools._project_migration_harness.project_completion_verifier_phase import (
    advance_project_verifier_phase,
)
from validation.tools._project_migration_harness.project_repair_authoritative_ir import (
    persist_authoritative_project_ir,
)
from validation.tools._project_migration_harness.project_verifier_repair_flow import (
    settle_pending_project_verifier_repair,
)
from validation.tools.project_migration_gate_authority_test_support import (
    ProjectMigrationGateAuthorityCase,
)
from validation.tools.project_migration_project_verifier_repair_test_support import (
    ProjectVerifierRepairFlowSupportMixin,
)


class ProjectMigrationProjectVerifierRepairTests(
    ProjectVerifierRepairFlowSupportMixin, ProjectMigrationGateAuthorityCase,
):
    def setUp(self) -> None:
        super().setUp()
        self._prepare_verifier_case()

    def test_v2_receipt_is_recomputed_and_registered_in_shared_queue(self) -> None:
        receipt = coordinate_project_interfaces(
            self.rust_project_ir,
            project_diagnostic_intakes=self.wrappers,
        )
        self.assertEqual(2, receipt["schema_version"])
        self.assertEqual("repair-required", receipt["status"])
        self.assertEqual(2, receipt["project_repair_queue"]["item_count"])
        self.assertEqual(2, len(receipt["project_verifier_diagnostic_sha256s"]))
        self.assertEqual(receipt, validate_coordinator_receipt(receipt))
        registration = self.ledger.register_project_interface_receipt(
            run_id="run", receipt=receipt,
            rust_project_ir=self.rust_project_ir,
        )
        self.assertEqual(2, registration.receipt_epoch)
        loaded = self.ledger.load_project_interface_receipt(
            run_id="run",
            queue_sha256=receipt["project_repair_queue"][
                "project_repair_queue_sha256"
            ],
        )
        self.assertEqual(receipt, loaded)

    def test_initial_intake_phase_registers_without_provider_or_attempt(self) -> None:
        ir_ref = persist_authoritative_project_ir(
            self.rust_project_ir, out_root=self.out_root,
            out_root_rel="target/run",
        )
        result = advance_project_verifier_phase(
            ledger=self.ledger, run_id="run", harness_root=self.harness,
            integration={"authoritative_rust_project_ir": ir_ref},
            cargo_result={
                "status": "failed", "project_diagnostic_intakes": [self.reference],
            },
        )
        self.assertEqual("waiting", result["status"])
        self.assertEqual("project-diagnostic-intake-registered", result["stage"])
        with self.ledger.connect() as connection:
            attempts = connection.execute(
                "select count(*) from project_repair_attempts where run_id='run'"
            ).fetchone()[0]
        self.assertEqual(0, attempts)
        self.assertEqual(0, self.ledger.project_repair_budget(
            run_id="run",
        ).provider_calls)

    def test_verifier_diagnostic_context_contains_bounded_host_detail(self) -> None:
        receipt = coordinate_project_interfaces(
            self.rust_project_ir,
            project_diagnostic_intakes=self.wrappers,
        )
        item = next(
            value for value in receipt["project_repair_queue"]["items"]
            if value["diagnostic_code"] == "project-verifier-e0432"
        )
        context = build_project_repair_context(
            self.rust_project_ir, receipt, receipt_epoch=2,
            repair_id=item["repair_id"],
            project_diagnostic_intakes=self.wrappers,
        )
        self.assertEqual(2, context["schema_version"])
        self.assertEqual("host-project-verifier", context["diagnostic"]["origin"])
        self.assertEqual("unresolved import `shared`", context["diagnostic"]["message"])
        self.assertNotIn("raw_output", context["diagnostic"])

        tampered = copy.deepcopy(context)
        tampered["diagnostic"]["message"] = ""
        tampered["context_sha256"] = content_sha256({
            key: value for key, value in tampered.items()
            if key != "context_sha256"
        })
        with self.assertRaisesRegex(ValueError, "verifier diagnostic context"):
            validate_project_repair_context(tampered)

        for field, invalid in (("stage", []), ("location", {
            "file": 1, "line": 1, "column": 1,
        })):
            malformed = copy.deepcopy(context)
            malformed["diagnostic"][field] = invalid
            malformed["context_sha256"] = content_sha256({
                key: value for key, value in malformed.items()
                if key != "context_sha256"
            })
            with self.assertRaises(ValueError):
                validate_project_repair_context(malformed)

    def test_registered_v2_receipt_rejects_stale_candidate_set(self) -> None:
        receipt = coordinate_project_interfaces(
            self.rust_project_ir,
            project_diagnostic_intakes=self.wrappers,
        )
        self.ledger.register_project_interface_receipt(
            run_id="run", receipt=receipt,
            rust_project_ir=self.rust_project_ir,
        )
        self.candidate_id, self.candidate_sha = self.make_candidate("candidate-two")
        self.promote_current_candidate()
        with self.assertRaisesRegex(LedgerError, "current last-good"):
            self.ledger.load_project_interface_receipt(
                run_id="run",
                queue_sha256=receipt["project_repair_queue"][
                    "project_repair_queue_sha256"
                ],
            )

    def test_model_candidate_waits_for_fresh_project_verifier_pass(self) -> None:
        source_receipt, request, result, candidate, pending = self._candidate()
        self.assertEqual("pending-reverification", result["status"])
        self.assertEqual("candidate-ready", result["ledger_status"])
        self.assertEqual("pending-reverification", pending["status"])
        epoch, latest = self.ledger.load_latest_project_interface_receipt(
            run_id="run",
        )
        self.assertEqual(2, epoch)
        self.assertEqual(source_receipt, latest)
        projection = self.ledger.project_repair_projection(
            run_id="run",
            queue_sha256=request["project_repair_queue_sha256"],
            repair_id=request["repair_id"],
        )
        self.assertEqual("candidate-ready", projection.status)
        self.assertEqual(candidate["ir_sha256"], projection.candidate_ir_sha256)

    def test_fresh_recorded_pass_resolves_verifier_candidate(self) -> None:
        _receipt, request, _result, candidate, pending = self._candidate()
        record = self._record_candidate_gate(candidate, "passed", "generation-two")
        cargo_result = self._cargo_result("passed", record)
        unrelated = copy.deepcopy(record)
        unrelated["gate_kind"] = "cargo-test"
        cargo_result["records"].append(unrelated)
        settled = settle_pending_project_verifier_repair(
            ledger=self.ledger, run_id="run", rust_project_ir=candidate,
            pending=pending, cargo_result=cargo_result,
        )
        self.assertEqual("verified", settled["status"])
        projection = self.ledger.project_repair_projection(
            run_id="run", queue_sha256=request["project_repair_queue_sha256"],
            repair_id=request["repair_id"],
        )
        self.assertEqual("resolved", projection.status)
        source = self.ledger.load_project_interface_receipt(
            run_id="run", queue_sha256=request["project_repair_queue_sha256"],
        )
        sibling = next(
            item for item in source["project_repair_queue"]["items"]
            if item["repair_id"] != request["repair_id"]
        )
        sibling_state = self.ledger.project_repair_projection(
            run_id="run", queue_sha256=request["project_repair_queue_sha256"],
            repair_id=sibling["repair_id"],
        )
        self.assertEqual("cancelled", sibling_state.status)
        epoch, latest = self.ledger.load_latest_project_interface_receipt(
            run_id="run",
        )
        self.assertEqual(3, epoch)
        self.assertEqual(1, latest["schema_version"])
        self.assertEqual(candidate["ir_sha256"], latest["rust_project_ir_sha256"])

    def test_static_receipt_cannot_resolve_verifier_origin_candidate(self) -> None:
        _receipt, request, _result, candidate, _pending = self._candidate()
        static_receipt = coordinate_project_interfaces(candidate)
        self.ledger.register_project_interface_receipt(
            run_id="run", receipt=static_receipt, rust_project_ir=candidate,
        )
        projection = self.ledger.project_repair_projection(
            run_id="run", queue_sha256=request["project_repair_queue_sha256"],
            repair_id=request["repair_id"],
        )
        with self.assertRaisesRegex(LedgerError, "target-reducing"):
            self.ledger.resolve_project_repair_candidate(
                run_id="run",
                queue_sha256=request["project_repair_queue_sha256"],
                repair_id=request["repair_id"], command_id="forged-static-resolve",
                expected_version=projection.version,
                coordinator_receipt_sha256=static_receipt[
                    "coordinator_receipt_sha256"
                ],
            )
        with self.ledger.connect() as connection, self.assertRaisesRegex(
            LedgerError, "historical repair obligations",
        ):
            require_project_interface_ready(connection, "run")

    def test_pass_rejects_same_generation_and_unrecorded_epoch(self) -> None:
        _receipt, _request, _result, candidate, pending = self._candidate()
        same_generation = self._record_candidate_gate(
            candidate, "passed", "source-generation",
        )
        with self.assertRaisesRegex(LedgerError, "new generation"):
            settle_pending_project_verifier_repair(
                ledger=self.ledger, run_id="run", rust_project_ir=candidate,
                pending=pending,
                cargo_result=self._cargo_result("passed", same_generation),
            )
        forged = copy.deepcopy(same_generation)
        forged["gate_epoch"] += 1
        with self.assertRaisesRegex(LedgerError, "ledger authoritative"):
            settle_pending_project_verifier_repair(
                ledger=self.ledger, run_id="run", rust_project_ir=candidate,
                pending=pending, cargo_result=self._cargo_result("passed", forged),
            )
        wrong_size = copy.deepcopy(same_generation)
        wrong_size["evidence"]["size_bytes"] += 1
        with self.assertRaisesRegex(LedgerError, "evidence size binding"):
            settle_pending_project_verifier_repair(
                ledger=self.ledger, run_id="run", rust_project_ir=candidate,
                pending=pending,
                cargo_result=self._cargo_result("passed", wrong_size),
            )

    def test_pass_rejects_generation_changed_after_gate_record(self) -> None:
        _receipt, _request, _result, candidate, pending = self._candidate()
        record = self._record_candidate_gate(candidate, "passed", "generation-two")
        self._prepare_source_generation()
        with self.assertRaisesRegex(LedgerError, "generation binding drifted"):
            settle_pending_project_verifier_repair(
                ledger=self.ledger, run_id="run", rust_project_ir=candidate,
                pending=pending, cargo_result=self._cargo_result("passed", record),
            )

    def test_failed_recheck_rolls_back_and_inherits_attempt_budget(self) -> None:
        _receipt, request, _result, candidate, pending = self._candidate()
        record = self._record_candidate_gate(candidate, "failed", "generation-two")
        settled = settle_pending_project_verifier_repair(
            ledger=self.ledger, run_id="run", rust_project_ir=candidate,
            pending=pending, cargo_result=self._cargo_result("failed", record),
        )
        self.assertEqual("repair-required", settled["status"])
        old = self.ledger.project_repair_projection(
            run_id="run", queue_sha256=request["project_repair_queue_sha256"],
            repair_id=request["repair_id"],
        )
        self.assertEqual("cancelled", old.status)
        epoch, latest = self.ledger.load_latest_project_interface_receipt(
            run_id="run",
        )
        self.assertEqual(3, epoch)
        self.assertEqual(2, latest["schema_version"])
        new_item = latest["project_repair_queue"]["items"][0]
        current = self.ledger.project_repair_projection(
            run_id="run",
            queue_sha256=latest["project_repair_queue"][
                "project_repair_queue_sha256"
            ],
            repair_id=new_item["repair_id"],
        )
        self.assertEqual("queued", current.status)
        self.assertEqual(1, current.attempt_count)

if __name__ == "__main__":
    unittest.main()
