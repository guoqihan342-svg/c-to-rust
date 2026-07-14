from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import PurePosixPath
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.context_frontier_refresh import (
    refresh_single_scc_context,
)
from validation.tools._project_migration_harness.context_frontier import (
    materialize_scheduled_contexts,
)
from validation.tools._project_migration_harness.context_frontier_overlay_runtime import (
    resolve_schedule_context_overlays,
)
from validation.tools._project_migration_harness.ledger_context_frontier_authority import (
    ContextFrontierAuthority, _ContextFrontierCommand,
)
from validation.tools._project_migration_harness.ledger_schema import atomic
from validation.tools._project_migration_harness.runtime_request_validation import (
    bound_worker_request,
)
from validation.tools._project_migration_harness.scheduler import schedule_portfolio
from validation.tools.project_migration_controller_test_support import (
    ProjectMigrationControllerCase,
)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


class ProjectMigrationContextFrontierRefreshTests(
    ProjectMigrationControllerCase,
):
    def test_single_scc_host_refresh_drives_overlay_bound_runtime_request(self) -> None:
        plan = self.plan("int unit(void) { return 1; }\n")
        ledger = self.ledger()
        original_assignments = deepcopy(plan["portfolio"]["assignments"])
        _materialize_initial_context(plan, ledger, self)
        current = ledger.context_frontier_states(plan["run_id"])[0]

        invalidated = _invalidate_frontier(ledger, current, "refresh-e2e")
        self.assertEqual(("pending_retrieval", 1), (
            invalidated.current.status, invalidated.current.version,
        ))
        blocked = self.dispatch(plan, ledger)
        self.assertEqual([], blocked["launches"])
        self.assertFalse(blocked["execution"]["model_launched"])
        self.assertEqual((0, 0), _attempt_lease_counts(ledger, plan["run_id"]))

        refreshed = _refresh(plan, ledger, self)
        frontier = ledger.context_frontier_states(plan["run_id"])[0]

        self.assertEqual("ready", refreshed["status"])
        self.assertTrue(refreshed["ledger"]["applied"])
        self.assertEqual(("ready", 2), (
            frontier["status"], frontier["state_version"],
        ))
        self.assertEqual(
            refreshed["context_overlay"], frontier["head"]["context_overlay"],
        )
        self.assertEqual(
            original_assignments, plan["portfolio"]["assignments"],
        )

        dispatch = self.dispatch(plan, ledger)
        self.assertTrue(dispatch["launches"])
        self.assertFalse(dispatch["execution"]["model_launched"])
        launch = dispatch["launches"][0]
        request = self.request(launch)
        reopened, attempt = bound_worker_request(
            launch["request"], ledger=ledger, harness_root=self.harness,
        )

        self.assertEqual(request, reopened)
        self.assertEqual(launch["attempt_id"], attempt["attempt_id"])
        self.assertEqual(
            refreshed["context_overlay"],
            request["context_frontier"]["context_overlay"],
        )
        self.assertEqual(frontier["head"]["catalog"], request["context"]["catalog"])
        self.assertNotEqual(
            original_assignments[0]["context"], request["context"],
        )
        with ledger.connect() as connection:
            events = connection.execute(
                """select command_kind,evidence_sha256
                   from context_frontier_events where run_id=? and unit_id=?
                   order by event_id""",
                (plan["run_id"], current["unit_id"]),
            ).fetchall()
        self.assertEqual(
            ["selection_invalidated", "selection_ready"],
            [row["command_kind"] for row in events],
        )
        self.assertEqual(
            refreshed["context_overlay"]["sha256"], events[-1]["evidence_sha256"],
        )

    def test_overlay_drift_blocks_dispatch_before_attempt_or_lease(self) -> None:
        plan = self.plan("int unit(void) { return 1; }\n")
        ledger = self.ledger()
        _materialize_initial_context(plan, ledger, self)
        current = ledger.context_frontier_states(plan["run_id"])[0]
        _invalidate_frontier(ledger, current, "refresh-overlay-drift")
        refreshed = _refresh(plan, ledger, self)
        overlay_path = self.harness.joinpath(
            *PurePosixPath(refreshed["context_overlay"]["path"]).parts
        )
        overlay_path.write_bytes(b"{}\n")

        with self.assertRaisesRegex(ValueError, "SHA-256 drifted"):
            self.dispatch(plan, ledger)
        self.assertEqual((0, 0), _attempt_lease_counts(ledger, plan["run_id"]))


def _refresh(plan: dict, ledger: object, case: ProjectMigrationControllerCase) -> dict:
    unit_id = plan["portfolio"]["ledger_units"][0]["unit_id"]
    return refresh_single_scc_context(
        plan["portfolio"],
        portfolio_reference=_plan_reference(plan, "portfolio"),
        context_bundle_reference=_plan_reference(plan, "context_pages"),
        ledger=ledger,
        harness_root=case.harness,
        out_root=case.out_root,
        out_root_rel="target/run",
        unit_id=unit_id,
    )


def _materialize_initial_context(
    plan: dict, ledger: object, case: ProjectMigrationControllerCase,
) -> None:
    schedule = schedule_portfolio(
        plan["portfolio"], ledger.unit_states(plan["run_id"]), {},
    )
    resolved = resolve_schedule_context_overlays(
        schedule, harness_root=case.harness,
    )
    materialize_scheduled_contexts(
        resolved,
        harness_root=case.harness,
        out_root=case.out_root,
        out_root_rel="target/run",
    )
    if _attempt_lease_counts(ledger, plan["run_id"]) != (0, 0):
        raise AssertionError("context fixture materialization created runtime state")


def _invalidate_frontier(
    ledger: object, current: dict, label: str,
):
    head = deepcopy(current["head"])
    binding = deepcopy(head["input_binding"])
    binding["failure_fact_set_sha256"] = digest(f"{label}:failure-facts")
    target = {
        **head,
        "status": "pending_retrieval",
        "mode": "host_retrieval",
        "query_epoch": head["query_epoch"] + 1,
        "input_binding": binding,
        "selection_input_sha256": content_sha256(binding),
        "context_overlay": None,
        "selection_receipt_sha256": None,
        "materialized_page_set_sha256": None,
        "selection_materialization_sha256": None,
    }
    command = _ContextFrontierCommand(
        command_kind="selection_invalidated",
        command_id=f"selection-invalidated:{label}",
        run_id=current["head"]["run_id"],
        unit_id=current["unit_id"],
        expected_status=current["status"],
        expected_version=current["state_version"],
        expected_head_sha256=current["head_sha256"],
        target_head=target,
        evidence_sha256=digest(f"{label}:invalidation-evidence"),
    )
    return _apply_authority(ledger, command)


def _apply_authority(ledger: object, command: _ContextFrontierCommand):
    with ledger.connect() as connection, atomic(connection):
        return ContextFrontierAuthority(connection).apply(command)


def _plan_reference(plan: dict, name: str) -> dict:
    reference = plan["artifacts"][name]
    return {
        **reference,
        "path": f"target/run/{reference['path']}",
    }


def _attempt_lease_counts(ledger: object, run_id: str) -> tuple[int, int]:
    with ledger.connect() as connection:
        attempts = int(connection.execute(
            "select count(*) from attempts where run_id=?", (run_id,),
        ).fetchone()[0])
        leases = int(connection.execute(
            "select count(*) from leases where run_id=?", (run_id,),
        ).fetchone()[0])
    return attempts, leases


if __name__ == "__main__":
    unittest.main()
