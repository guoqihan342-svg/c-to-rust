from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.project_interface_coordinator import (
    coordinate_project_interfaces,
)
from validation.tools._project_migration_harness.rust_project_ir import (
    build_rust_project_ir,
)
from validation.tools._project_migration_harness.project_repair_lineage import (
    derive_project_repair_diagnostic_lineage,
)
from validation.tools.project_migration_project_repair_test_support import (
    coordinated_case, sha,
)


class ProjectRepairBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-repair-budget-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.ledger = ProjectLedger(self.root / "ledger.sqlite3")
        self.ledger.create_run(
            run_id="run", project_key="generic-project", source_commit="commit",
            dag_sha256=sha("dag"), units=[{
                "unit_id": "unit-a", "group_id": "unit-a", "wave_index": 0,
                "content_sha256": sha("unit-a"),
            }], assignments=[], max_concurrency=2, max_attempts=3,
        )

    def test_diagnostic_attempt_budget_is_inherited_across_receipt_epochs(self) -> None:
        base, first = coordinated_case(
            "budget-lineage", max_attempts=2, additional_conflict=True,
        )
        self._register(base, first)
        items = first["project_repair_queue"]["items"]
        persistent, repaired_elsewhere = items[0], items[1]
        self._fail_attempt(first, persistent, "first")

        by_sha = {
            value["diagnostic_sha256"]: value for value in first["diagnostics"]
        }
        public_ids = {
            value["declaration_id"] for value in base["public_api"]
        }
        removed_id = next(
            value for value in by_sha[
                repaired_elsewhere["diagnostic_sha256"]
            ]["entity_ids"]
            if value in public_ids
        )
        second_ir = _rebuild(
            base, [
                value for value in base["public_api"]
                if value["declaration_id"] != removed_id
            ],
        )
        second = coordinate_project_interfaces(
            second_ir, max_repairs=32, max_attempts_per_item=2,
        )
        second_item = _item(second, persistent["diagnostic_sha256"])
        self._register(second_ir, second)
        second_projection = self.ledger.project_repair_projection(
            run_id="run",
            queue_sha256=second["project_repair_queue"][
                "project_repair_queue_sha256"
            ],
            repair_id=second_item["repair_id"],
        )
        self.assertEqual(("queued", 0, 1), (
            second_projection.status, second_projection.version,
            second_projection.attempt_count,
        ))
        self._fail_attempt(second, second_item, "second")

        unique = dict(second_ir["public_api"][0])
        unique.update({
            "declaration_id": "api-budget-lineage-unique",
            "symbol": "budget_lineage_unique", "signature": "fn()->usize",
        })
        third_ir = _rebuild(second_ir, [*second_ir["public_api"], unique])
        third = coordinate_project_interfaces(
            third_ir, max_repairs=32, max_attempts_per_item=2,
        )
        third_item = _item(third, persistent["diagnostic_sha256"])
        self._register(third_ir, third)
        exhausted = self.ledger.project_repair_projection(
            run_id="run",
            queue_sha256=third["project_repair_queue"][
                "project_repair_queue_sha256"
            ],
            repair_id=third_item["repair_id"],
        )
        self.assertEqual(("exhausted", 0, 2), (
            exhausted.status, exhausted.version, exhausted.attempt_count,
        ))
        budget = self.ledger.project_repair_budget(run_id="run")
        self.assertEqual((0, 3), (budget.provider_calls, budget.receipt_epochs))

    def test_two_executors_claim_only_one_provider_launch(self) -> None:
        rust_ir, receipt = coordinated_case("launch-claim")
        self._register(rust_ir, receipt)
        item = receipt["project_repair_queue"]["items"][0]
        queue_sha = receipt["project_repair_queue"][
            "project_repair_queue_sha256"
        ]
        started = self.ledger.start_project_repair_attempt(
            run_id="run", queue_sha256=queue_sha,
            repair_id=item["repair_id"], command_id="launch-claim-start",
            expected_status="queued", expected_version=0,
            worker_id="project-repairer-budget",
            input_sha256=sha("launch-claim-input"),
        )

        def claim(_index: int) -> bool:
            return self.ledger.mark_project_repair_command_started(
                attempt_id=started.attempt_id,
                worker_id="project-repairer-budget",
                expected_version=started.current.version,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(claim, range(2)))
        self.assertCountEqual([True, False], results)
        budget = self.ledger.project_repair_budget(run_id="run")
        self.assertEqual(1, budget.provider_calls)

    def test_lineage_survives_candidate_derived_module_id_change(self) -> None:
        first = {
            "code": "conflicting_public_api",
            "entity_ids": ["module-from-candidate-a", "shared"],
            "affected_module_ids": ["module-from-candidate-a"],
        }
        second = {
            **first,
            "entity_ids": ["module-from-candidate-b", "shared"],
            "affected_module_ids": ["module-from-candidate-b"],
        }
        first_ir = {"modules": [{
            "module_id": "module-from-candidate-a", "unit_id": "unit-a",
            "rust_path": "src/unit_a.rs",
        }]}
        second_ir = {"modules": [{
            "module_id": "module-from-candidate-b", "unit_id": "unit-a",
            "rust_path": "src/unit_a.rs",
        }]}
        self.assertEqual(
            derive_project_repair_diagnostic_lineage(first, first_ir),
            derive_project_repair_diagnostic_lineage(second, second_ir),
        )

    def _register(self, rust_ir: dict, receipt: dict) -> None:
        self.ledger.register_project_interface_receipt(
            run_id="run", receipt=receipt, rust_project_ir=rust_ir,
        )

    def _fail_attempt(self, receipt: dict, item: dict, label: str) -> None:
        queue_sha = receipt["project_repair_queue"][
            "project_repair_queue_sha256"
        ]
        projection = self.ledger.project_repair_projection(
            run_id="run", queue_sha256=queue_sha,
            repair_id=item["repair_id"],
        )
        started = self.ledger.start_project_repair_attempt(
            run_id="run", queue_sha256=queue_sha,
            repair_id=item["repair_id"], command_id=f"start-{label}",
            expected_status=projection.status,
            expected_version=projection.version,
            worker_id="project-repairer-budget",
            input_sha256=sha(f"input-{label}"),
            metadata={"artifact_root": "target/project-repair"},
        )
        evidence = sha(f"failure-{label}")
        self.ledger.record_project_repair_artifact(
            attempt_id=started.attempt_id,
            artifact_id=f"failure-{label}", kind="test-evidence",
            repo_rel_path=f"target/project-repair/failure-{label}.json",
            content_sha256=evidence, status="failed",
        )
        self.ledger.finish_project_repair_attempt(
            attempt_id=started.attempt_id, command_id=f"finish-{label}",
            expected_version=started.current.version,
            worker_id="project-repairer-budget", outcome="failed",
            evidence_sha256=evidence, error_key="bounded_repair_failed",
        )


def _item(receipt: dict, diagnostic_sha256: str) -> dict:
    return next(
        value for value in receipt["project_repair_queue"]["items"]
        if value["diagnostic_sha256"] == diagnostic_sha256
    )


def _rebuild(ir: dict, public_api: list[dict]) -> dict:
    return build_rust_project_ir(
        migration_dag_ref=ir["bindings"]["migration_dag"],
        build_ir_refs=ir["bindings"]["build_ir"],
        candidate_refs=ir["bindings"]["candidates"], crate=ir["crate"],
        modules=ir["modules"], public_api=public_api,
        shared_types=ir["shared_types"],
        global_ownership=ir["global_ownership"],
        initialization=ir["initialization"],
        ffi_boundaries=ir["ffi_boundaries"], cfgs=ir["cfgs"],
        features=ir["features"], unsafe_obligations=ir["unsafe_obligations"],
    )


if __name__ == "__main__":
    unittest.main()
