from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.ledger_context_frontier_authority import (
    ContextFrontierAuthority, _ContextFrontierCommand,
)
from validation.tools._project_migration_harness.ledger_schema import atomic
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools.project_migration_controller_test_support import (
    ProjectMigrationControllerCase,
)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


class ProjectMigrationContextFrontierRuntimeBindingTests(
    ProjectMigrationControllerCase,
):
    def test_portfolio_binding_rejects_missing_context_frontier_row(self) -> None:
        plan = self.plan("int unit(void) { return 1; }\n")
        ledger = self.ledger()
        frontier = ledger.context_frontier_states(plan["run_id"])[0]

        with ledger.connect() as connection:
            deleted = connection.execute(
                "delete from context_frontiers where run_id=? and unit_id=?",
                (plan["run_id"], frontier["unit_id"]),
            )
            self.assertEqual(1, deleted.rowcount)

        with self.assertRaisesRegex(LedgerError, "context frontiers drifted"):
            ledger.require_portfolio_binding(plan["portfolio"])

    def test_portfolio_binding_rejects_projection_event_replay_drift(self) -> None:
        plan = self.plan("int unit(void) { return external_api(); }\n")
        ledger = self.ledger()
        pending = ledger.context_frontier_states(plan["run_id"])[0]
        result = _apply_authority(ledger, _ContextFrontierCommand(
            command_kind="selection_ready",
            command_id="selection-ready:runtime-binding",
            run_id=plan["run_id"],
            unit_id=pending["unit_id"],
            expected_status=pending["status"],
            expected_version=pending["state_version"],
            expected_head_sha256=pending["head_sha256"],
            target_head=_ready_head(pending["head"]),
            evidence_sha256=digest("runtime-binding-ready-evidence"),
        ))
        self.assertTrue(result.applied)

        with ledger.connect() as connection:
            event_count = connection.execute(
                """select count(*) from context_frontier_events
                   where run_id=? and unit_id=?""",
                (plan["run_id"], pending["unit_id"]),
            ).fetchone()[0]
            self.assertEqual(1, event_count)
            connection.execute(
                """update context_frontiers set state_version=state_version+1
                   where run_id=? and unit_id=?""",
                (plan["run_id"], pending["unit_id"]),
            )

        with self.assertRaisesRegex(
            LedgerError, "projection does not match immutable events",
        ):
            ledger.require_portfolio_binding(plan["portfolio"])

    def test_command_start_rejects_post_attempt_projection_drift(self) -> None:
        plan = self.plan("int unit(void) { return 1; }\n")
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        ledger.bind_attempt_preflight(
            attempt_id=launch["attempt_id"],
            owner=launch["worker_id"],
            fencing_token=launch["fencing_token"],
            preflight_path="target/run/harness/preflight.json",
            preflight_sha256=digest("runtime-binding-preflight"),
        )
        ledger.authorize_command_launch(
            attempt_id=launch["attempt_id"],
            owner=launch["worker_id"],
            fencing_token=launch["fencing_token"],
        )

        with ledger.connect() as connection:
            connection.execute(
                """update context_frontiers set state_version=state_version+1
                   where run_id=? and unit_id=?""",
                (plan["run_id"], launch["unit_id"]),
            )

        with self.assertRaisesRegex(
            LedgerError, "projection does not match immutable events",
        ):
            ledger.mark_command_started(
                attempt_id=launch["attempt_id"],
                owner=launch["worker_id"],
                fencing_token=launch["fencing_token"],
            )

        with ledger.connect() as connection:
            attempt = connection.execute(
                "select metadata_json from attempts where attempt_id=?",
                (launch["attempt_id"],),
            ).fetchone()
            command_started_events = connection.execute(
                """select count(*) from transitions where run_id=? and unit_id=?
                   and command_kind='worker_command_started'""",
                (plan["run_id"], launch["unit_id"]),
            ).fetchone()[0]
        metadata = json.loads(attempt["metadata_json"])
        self.assertIs(metadata["command_started"], False)
        self.assertNotIn("command_started_at", metadata)
        self.assertEqual(0, command_started_events)


def _ready_head(pending: dict) -> dict:
    return {
        **deepcopy(pending),
        "status": "ready",
        "context_overlay": _overlay_reference("runtime-binding-overlay"),
        "selection_receipt_sha256": digest("runtime-binding-receipt"),
        "materialized_page_set_sha256": digest("runtime-binding-pages"),
        "selection_materialization_sha256": content_sha256({
            "receipt": "runtime-binding-receipt",
            "pages": "runtime-binding-pages",
        }),
    }


def _apply_authority(ledger: object, command: _ContextFrontierCommand):
    with ledger.connect() as connection, atomic(connection):
        return ContextFrontierAuthority(connection).apply(command)


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
