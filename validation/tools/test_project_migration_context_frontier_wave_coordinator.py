from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.context_frontier_wave_coordinator import (
    prepare_next_context_frontier_wave,
)
from validation.tools.project_migration_controller_test_support import (
    ProjectMigrationControllerCase,
)


SOURCE = (
    "int alpha(int value) { return value + 1; }\n"
    "int beta(int value) { return alpha(value); }\n"
)


class ProjectMigrationContextFrontierWaveCoordinatorTests(
    ProjectMigrationControllerCase,
):
    def test_last_good_wave_is_refreshed_without_launch(self) -> None:
        plan = self.plan(SOURCE)
        ledger = self.ledger()
        dag = self.load(_path(plan, "portfolio_dag"))
        context = self.load(_path(plan, "context_pages"))
        previous = dag["waves"][0]["group_ids"]
        following = dag["waves"][1]["group_ids"]
        _mark_last_good(ledger, plan["run_id"], previous)

        result = prepare_next_context_frontier_wave(
            plan["portfolio"],
            portfolio_reference=_reference(plan, "portfolio"),
            latest_dag=dag,
            latest_dag_reference=_reference(plan, "portfolio_dag"),
            context_bundle=context,
            context_bundle_reference=_reference(plan, "context_pages"),
            completed_wave_index=0,
            failure_evidence=[],
            expansion_queries=[],
            ledger=ledger,
            harness_root=self.harness,
            out_root=self.out_root,
            out_root_rel="target/run",
        )

        self.assertEqual("ready", result["status"])
        self.assertEqual(following, [
            item["unit_id"] for item in result["selection_directives"]
        ])
        self.assertTrue(all(
            item["selection_ready"] is True
            and item["requires_host_recompute"] is False
            for item in result["selection_directives"]
        ))
        frontiers = {
            item["unit_id"]: item
            for item in ledger.context_frontier_states(plan["run_id"])
        }
        self.assertTrue(all(
            frontiers[unit_id]["status"] == "ready"
            and frontiers[unit_id]["state_version"] == 2
            and frontiers[unit_id]["head"]["query_epoch"] == 1
            and isinstance(frontiers[unit_id]["head"]["context_overlay"], dict)
            for unit_id in following
        ))
        self.assertEqual(len(following), len(result["ledger"]["invalidations"]))
        self.assertEqual(len(following), len(result["ledger"]["refreshes"]))
        with ledger.connect() as connection:
            attempts = connection.execute(
                "select count(*) from attempts where run_id=?", (plan["run_id"],),
            ).fetchone()[0]
            leases = connection.execute(
                "select count(*) from leases where run_id=?", (plan["run_id"],),
            ).fetchone()[0]
        self.assertEqual((0, 0), (attempts, leases))

    def test_incomplete_previous_wave_fails_before_frontier_event(self) -> None:
        plan = self.plan(SOURCE)
        ledger = self.ledger()
        dag = self.load(_path(plan, "portfolio_dag"))
        context = self.load(_path(plan, "context_pages"))

        with self.assertRaisesRegex(ValueError, "not last-good complete"):
            prepare_next_context_frontier_wave(
                plan["portfolio"],
                portfolio_reference=_reference(plan, "portfolio"),
                latest_dag=dag,
                latest_dag_reference=_reference(plan, "portfolio_dag"),
                context_bundle=context,
                context_bundle_reference=_reference(plan, "context_pages"),
                completed_wave_index=0,
                failure_evidence=[],
                expansion_queries=[],
                ledger=ledger,
                harness_root=self.harness,
                out_root=self.out_root,
                out_root_rel="target/run",
            )
        with ledger.connect() as connection:
            count = connection.execute(
                "select count(*) from context_frontier_events where run_id=?",
                (plan["run_id"],),
            ).fetchone()[0]
        self.assertEqual(0, count)


def _mark_last_good(ledger: object, run_id: str, unit_ids: list[str]) -> None:
    with ledger.connect() as connection:
        connection.execute("pragma foreign_keys=off")
        for unit_id in unit_ids:
            connection.execute(
                """update migration_units set status='resume-ready',
                   resumable_status='last_good',last_good_artifact_id=?
                   where run_id=? and unit_id=?""",
                (f"test-last-good-{unit_id}", run_id, unit_id),
            )
        connection.commit()


def _path(plan: dict, name: str) -> str:
    return f"target/run/{plan['artifacts'][name]['path']}"


def _reference(plan: dict, name: str) -> dict:
    value = plan["artifacts"][name]
    return {**value, "path": _path(plan, name)}


if __name__ == "__main__":
    unittest.main()
