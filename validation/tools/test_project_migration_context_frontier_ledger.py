from __future__ import annotations

from copy import deepcopy
import hashlib
import sqlite3
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.ledger_context_frontier import (
    prepare_portfolio_frontiers,
)
from validation.tools._project_migration_harness.ledger_context_frontier_authority import (
    ContextFrontierAuthority, _ContextFrontierCommand,
    assert_context_frontier_projection,
)
from validation.tools._project_migration_harness.ledger_schema import atomic
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools.project_migration_controller_test_support import (
    ProjectMigrationControllerCase,
)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


class ProjectMigrationContextFrontierLedgerTests(ProjectMigrationControllerCase):
    def test_pending_frontier_is_orthogonal_to_migration_unit_lifecycle(self) -> None:
        plan = self.plan("int unit(void) { return external_api(); }\n")
        ledger = self.ledger()

        frontiers = ledger.context_frontier_states(plan["run_id"])
        units = ledger.unit_states(plan["run_id"])

        self.assertEqual(1, len(frontiers))
        self.assertEqual("pending_retrieval", frontiers[0]["status"])
        self.assertEqual(0, frontiers[0]["state_version"])
        self.assertEqual("host_retrieval", frontiers[0]["head"]["mode"])
        self.assertEqual(("pending", "ready"), (
            units[0]["status"], units[0]["resumable_status"],
        ))

    def test_closed_context_starts_with_a_ready_frontier(self) -> None:
        plan = self.plan("int unit(void) { return 1; }\n")
        frontier = self.ledger().context_frontier_states(plan["run_id"])[0]

        self.assertEqual("ready", frontier["status"])
        self.assertEqual("host_retrieval", frontier["head"]["mode"])
        self.assertEqual(64, len(frontier["head"]["selection_receipt_sha256"]))
        self.assertEqual(64, len(frontier["head"]["materialized_page_set_sha256"]))

    def test_initial_frontier_hash_drift_is_rejected(self) -> None:
        plan = self.plan("int unit(void) { return external_api(); }\n")
        portfolio = deepcopy(plan["portfolio"])
        portfolio["context_frontiers"][0]["initial_head"]["query_epoch"] = 1

        with self.assertRaisesRegex(ValueError, "binding drifted"):
            prepare_portfolio_frontiers(
                portfolio,
                run_id=plan["run_id"],
                unit_ids=[portfolio["ledger_units"][0]["unit_id"]],
            )

    def test_frontier_cas_replay_invalidation_and_event_immutability(self) -> None:
        plan = self.plan("int unit(void) { return external_api(); }\n")
        ledger = self.ledger()
        pending = ledger.context_frontier_states(plan["run_id"])[0]
        ready_head = _ready_head(pending["head"])
        ready = _ContextFrontierCommand(
            command_kind="selection_ready",
            command_id="selection-ready:one",
            run_id=plan["run_id"],
            unit_id=pending["unit_id"],
            expected_status=pending["status"],
            expected_version=pending["state_version"],
            expected_head_sha256=pending["head_sha256"],
            target_head=ready_head,
            evidence_sha256=digest("ready-evidence"),
        )

        applied = _apply_authority(ledger, ready)
        replay = _apply_authority(ledger, ready)

        self.assertTrue(applied.applied)
        self.assertFalse(replay.applied)
        self.assertEqual((0, 1), (
            applied.previous.version,
            applied.current.version,
        ))
        invalidated_head = _invalidated_head(ready_head)
        invalidated = _apply_authority(ledger, _ContextFrontierCommand(
            command_kind="selection_invalidated",
            command_id="selection-invalidated:one",
            run_id=plan["run_id"],
            unit_id=pending["unit_id"],
            expected_status="ready",
            expected_version=1,
            expected_head_sha256=content_sha256(ready_head),
            target_head=invalidated_head,
            evidence_sha256=digest("failure-facts"),
        ))
        self.assertEqual(("pending_retrieval", 2), (
            invalidated.current.status,
            invalidated.current.version,
        ))
        with ledger.connect() as connection:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute(
                    "update context_frontier_events set command_id='changed'",
                )
            connection.execute(
                """update context_frontiers set state_version=1
                   where run_id=? and unit_id=?""",
                (plan["run_id"], pending["unit_id"]),
            )
            with self.assertRaisesRegex(LedgerError, "immutable events"):
                assert_context_frontier_projection(
                    connection, plan["run_id"], pending["unit_id"],
                )

    def test_stale_expected_head_is_rejected_after_aba(self) -> None:
        plan = self.plan("int unit(void) { return external_api(); }\n")
        ledger = self.ledger()
        pending = ledger.context_frontier_states(plan["run_id"])[0]
        command = _ContextFrontierCommand(
            command_kind="selection_ready", command_id="selection-ready:first",
            run_id=plan["run_id"], unit_id=pending["unit_id"],
            expected_status="pending_retrieval", expected_version=0,
            expected_head_sha256=pending["head_sha256"],
            target_head=_ready_head(pending["head"]),
            evidence_sha256=digest("first"),
        )
        _apply_authority(ledger, command)
        stale = _ContextFrontierCommand(
            command_kind="selection_ready", command_id="selection-ready:stale",
            run_id=command.run_id, unit_id=command.unit_id,
            expected_status=command.expected_status,
            expected_version=command.expected_version,
            expected_head_sha256=command.expected_head_sha256,
            target_head=command.target_head, evidence_sha256=digest("stale"),
        )

        with self.assertRaisesRegex(LedgerError, "stale"):
            _apply_authority(ledger, stale)


def _apply_authority(ledger: object, command: _ContextFrontierCommand):
    with ledger.connect() as connection, atomic(connection):
        return ContextFrontierAuthority(connection).apply(command)


def _ready_head(pending: dict) -> dict:
    return {
        **deepcopy(pending),
        "status": "ready",
        "context_overlay": _overlay_reference("ready-overlay"),
        "selection_receipt_sha256": digest("receipt"),
        "materialized_page_set_sha256": digest("pages"),
        "selection_materialization_sha256": digest("materialization"),
    }


def _invalidated_head(ready: dict) -> dict:
    binding = deepcopy(ready["input_binding"])
    binding["failure_fact_set_sha256"] = digest("new-failure-set")
    return {
        **deepcopy(ready),
        "status": "pending_retrieval",
        "query_epoch": ready["query_epoch"] + 1,
        "input_binding": binding,
        "selection_input_sha256": content_sha256(binding),
        "context_overlay": None,
        "selection_receipt_sha256": None,
        "materialized_page_set_sha256": None,
        "selection_materialization_sha256": None,
    }


def _overlay_reference(label: str) -> dict:
    value = digest(label)
    return {
        "path": (
            "target/run/context/frontier-cas/context-frontier-overlay/"
            f"sha256/{value[:2]}/{value}.json"
        ),
        "sha256": value,
        "size_bytes": 1,
    }


if __name__ == "__main__":
    unittest.main()
