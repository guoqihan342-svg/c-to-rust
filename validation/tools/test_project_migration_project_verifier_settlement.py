from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)
from validation.tools._project_migration_harness.ledger import LedgerError
from validation.tools._project_migration_harness.project_interface_coordinator import (
    coordinate_project_interfaces,
)
from validation.tools._project_migration_harness.project_revalidation_receipt import (
    project_revalidation_receipt,
)
from validation.tools.project_migration_gate_authority_test_support import (
    ProjectMigrationGateAuthorityCase,
)
from validation.tools.project_migration_project_verifier_repair_test_support import (
    ProjectVerifierRepairFlowSupportMixin,
)


class ProjectMigrationProjectVerifierSettlementTests(
    ProjectVerifierRepairFlowSupportMixin, ProjectMigrationGateAuthorityCase,
):
    def setUp(self) -> None:
        super().setUp()
        self._prepare_verifier_case()

    def test_low_level_pass_rejects_superseded_source_receipt(self) -> None:
        source, request, _result, candidate, _pending = self._candidate()
        record = self._record_candidate_gate(candidate, "passed", "generation-two")
        successor = coordinate_project_interfaces(candidate)
        revalidation = project_revalidation_receipt(
            run_id="run", source_receipt=source, candidate_ir=candidate,
            successor_receipt=successor,
            candidate_set_sha256=self.candidate_set, records=[record],
        )
        reference = write_content_addressed_json(
            self.out_root, "project-repair-revalidation", revalidation,
        )
        self.ledger.register_project_interface_receipt(
            run_id="run", receipt=successor, rust_project_ir=candidate,
        )
        projection = self.ledger.project_repair_projection(
            run_id="run", queue_sha256=request["project_repair_queue_sha256"],
            repair_id=request["repair_id"],
        )
        with self.assertRaisesRegex(LedgerError, "latest receipt"):
            self.ledger.settle_project_verifier_pass(
                run_id="run", queue_sha256=request["project_repair_queue_sha256"],
                repair_id=request["repair_id"], expected_version=projection.version,
                revalidation_reference=reference, successor_receipt=successor,
                rust_project_ir=candidate,
            )


if __name__ == "__main__":
    unittest.main()
