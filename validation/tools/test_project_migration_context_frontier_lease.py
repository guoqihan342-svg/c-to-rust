from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.ledger_context_frontier_authority import (
    ContextFrontierCommand,
)
from validation.tools._project_migration_harness.ledger_security import (
    LedgerError, LeaseConflict,
)
from validation.tools._project_migration_harness.scheduler import schedule_portfolio
from validation.tools.project_migration_controller_test_support import (
    ProjectMigrationControllerCase,
)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


class ProjectMigrationContextFrontierLeaseTests(ProjectMigrationControllerCase):
    def test_scheduler_and_attempt_bind_authoritative_frontier(self) -> None:
        plan = self.plan("int unit(void) { return 1; }\n")
        ledger = self.ledger()
        schedule = schedule_portfolio(
            plan["portfolio"], ledger.unit_states(plan["run_id"]), {},
        )

        self.assertEqual(1, len(schedule["ready"]))
        scheduled = schedule["ready"][0]
        self.assertEqual("ready", scheduled["context_frontier"]["status"])
        self.assertEqual(
            scheduled["launch_claim"]["context_frontier"],
            scheduled["context_frontier"],
        )
        self.assertEqual(64, len(schedule["schedule_sha256"]))
        launch = self.dispatch(plan, ledger)["launches"][0]
        attempt = ledger.running_attempt_for_worker(
            run_id=plan["run_id"], worker_id=launch["worker_id"],
        )
        metadata = json.loads(attempt["metadata_json"])
        self.assertEqual(
            scheduled["context_frontier"],
            metadata["launch_claim"]["context_frontier"],
        )

    def test_ledger_pending_frontier_overrides_forged_ready_assignment_context(self) -> None:
        plan = self.plan("int unit(void) { return external_api(); }\n")
        ledger = self.ledger()
        portfolio = {
            "limits": plan["portfolio"]["limits"],
            "assignments": deepcopy(plan["portfolio"]["assignments"]),
        }
        for assignment in portfolio["assignments"]:
            assignment["context"].pop("retrieval", None)

        schedule = schedule_portfolio(
            portfolio, ledger.unit_states(plan["run_id"]), {},
        )

        self.assertEqual([], schedule["ready"])
        self.assertTrue(all(
            item["reasons"] == ["context_retrieval_pending"]
            for item in schedule["deferred"]
        ))

    def test_missing_or_stale_frontier_claim_rolls_back_attempt_and_lease(self) -> None:
        plan = self.plan("int unit(void) { return 1; }\n")
        ledger = self.ledger()
        schedule = schedule_portfolio(
            plan["portfolio"], ledger.unit_states(plan["run_id"]), {},
        )
        ready = schedule["ready"][0]

        with self.assertRaisesRegex(LeaseConflict, "frontier binding"):
            ledger.begin_worker_attempt(
                run_id=plan["run_id"], assignment=ready["assignment"],
                ttl_seconds=900, input_sha256=digest("missing"),
                launch_claim=ready["launch_claim"],
                schedule_sha256=schedule["schedule_sha256"],
            )
        stale_frontier = deepcopy(ready["context_frontier"])
        stale_frontier["state_version"] += 1
        stale_claim = deepcopy(ready["launch_claim"])
        stale_claim["context_frontier"] = stale_frontier
        stale_claim["sha256"] = content_sha256({
            key: value for key, value in stale_claim.items() if key != "sha256"
        })
        with self.assertRaisesRegex(LeaseConflict, "stale"):
            ledger.begin_worker_attempt(
                run_id=plan["run_id"], assignment=ready["assignment"],
                ttl_seconds=900, input_sha256=digest("stale"),
                context_frontier=stale_frontier, launch_claim=stale_claim,
                schedule_sha256=schedule["schedule_sha256"],
            )
        self.assertEqual((0, 0), _attempt_lease_counts(ledger, plan["run_id"]))

    def test_split_lease_and_attempt_apis_are_rejected_for_portfolio_run(self) -> None:
        plan = self.plan("int unit(void) { return 1; }\n")
        ledger = self.ledger()
        assignment = plan["portfolio"]["assignments"][0]
        with self.assertRaisesRegex(LeaseConflict, "atomic begin_worker_attempt"):
            ledger.acquire_lease(
                run_id=plan["run_id"], unit_id=assignment["unit_id"],
                owner=assignment["worker_id"], ttl_seconds=900,
            )
        with ledger.connect() as connection:
            connection.execute(
                """insert into leases(run_id,unit_id,owner,role,status,fencing_token,
                   expires_at,heartbeat_at) values (?,?,?,?,'active',1,9999999999,1)""",
                (
                    plan["run_id"], assignment["unit_id"],
                    assignment["worker_id"], assignment["role"],
                ),
            )
        with self.assertRaisesRegex(LeaseConflict, "atomic begin_worker_attempt"):
            ledger.start_attempt(
                run_id=plan["run_id"], unit_id=assignment["unit_id"],
                role=assignment["role"], worker_id=assignment["worker_id"],
                fencing_token=1, input_sha256=digest("split"),
            )

    def test_active_attempt_prevents_frontier_invalidation(self) -> None:
        plan = self.plan("int unit(void) { return 1; }\n")
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        current = ledger.context_frontier_states(plan["run_id"])[0]
        target = _invalidated_head(current["head"])
        command = ContextFrontierCommand(
            command_kind="selection_invalidated",
            command_id="selection-invalidated:active",
            run_id=plan["run_id"], unit_id=current["unit_id"],
            expected_status=current["status"],
            expected_version=current["state_version"],
            expected_head_sha256=current["head_sha256"],
            target_head=target, evidence_sha256=digest("failure"),
        )

        with self.assertRaisesRegex(LedgerError, "active lease or attempt"):
            ledger.apply_context_frontier(command)
        self.assertEqual("running", ledger.running_attempt_for_worker(
            run_id=plan["run_id"], worker_id=launch["worker_id"],
        )["status"])

    def test_portfolio_bound_assignments_cannot_be_registered_late(self) -> None:
        plan = self.plan("int unit(void) { return 1; }\n")
        assignment = deepcopy(plan["portfolio"]["assignments"][0])
        assignment["worker_id"] = "late-worker"
        assignment["role"] = "planner"
        assignment["out_root"] = "target/run/workers/late-worker/out"

        with self.assertRaisesRegex(LedgerError, "immutable"):
            self.ledger().register_assignments(
                run_id=plan["run_id"], assignments=[assignment],
            )


def _invalidated_head(ready: dict) -> dict:
    binding = deepcopy(ready["input_binding"])
    binding["failure_fact_set_sha256"] = digest("changed-failure-set")
    return {
        **deepcopy(ready), "status": "pending_retrieval",
        "mode": "host_retrieval", "query_epoch": ready["query_epoch"] + 1,
        "input_binding": binding, "selection_input_sha256": content_sha256(binding),
        "selection_receipt_sha256": None, "materialized_page_set_sha256": None,
        "selection_materialization_sha256": None,
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
