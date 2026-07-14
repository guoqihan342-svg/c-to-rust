from __future__ import annotations

from collections import Counter
import unittest
from unittest import mock

from validation.tools._project_migration_harness import (
    context_frontier_wave_coordinator as wave_coordinator,
)
from validation.tools._project_migration_harness.context_frontier_refresh import (
    refresh_single_scc_context,
)
from validation.tools.project_migration_controller_test_support import (
    ProjectMigrationControllerCase,
)


SOURCE = (
    "int base(int value) { return value + 1; }\n"
    "int left(int value) { return base(value) + 2; }\n"
    "int right(int value) { return base(value) + 3; }\n"
    "int top(int value) { return left(value) + right(value); }\n"
)


class ProjectMigrationContextFrontierWaveResumeTests(
    ProjectMigrationControllerCase,
):
    def test_same_inputs_resume_partial_wave_without_duplicate_events(self) -> None:
        fixture = self._fixture()
        plan, ledger, targets = fixture["plan"], fixture["ledger"], fixture["targets"]
        inputs = _wave_inputs(self, fixture)
        real_refresh = wave_coordinator.refresh_single_scc_context
        refresh_calls = 0

        def fail_second_refresh(*args: object, **kwargs: object) -> dict:
            nonlocal refresh_calls
            refresh_calls += 1
            if refresh_calls == 2:
                raise RuntimeError("injected second context frontier refresh failure")
            return real_refresh(*args, **kwargs)

        with mock.patch.object(
            wave_coordinator,
            "refresh_single_scc_context",
            side_effect=fail_second_refresh,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "injected second context frontier refresh failure",
            ):
                wave_coordinator.prepare_next_context_frontier_wave(
                    plan["portfolio"], **inputs,
                )

        self.assertEqual(2, refresh_calls)
        partial = _target_states(ledger, plan["run_id"], targets)
        self.assertEqual(
            {
                targets[0]: ("ready", 2),
                targets[1]: ("pending_retrieval", 1),
            },
            {
                unit_id: (state["status"], state["state_version"])
                for unit_id, state in partial.items()
            },
        )
        partial_events = _events(ledger, plan["run_id"])
        self.assertEqual(
            Counter({
                (targets[0], "selection_invalidated"): 1,
                (targets[0], "selection_ready"): 1,
                (targets[1], "selection_invalidated"): 1,
            }),
            _event_kinds(partial_events),
        )
        self.assertEqual((0, 0), _runtime_counts(ledger, plan["run_id"]))

        try:
            result = wave_coordinator.prepare_next_context_frontier_wave(
                plan["portfolio"], **inputs,
            )
        except ValueError as error:
            self.fail(
                "same bounded inputs must resume the partial context frontier wave: "
                f"{error}"
            )

        final = _target_states(ledger, plan["run_id"], targets)
        self.assertEqual("ready", result["status"])
        self.assertTrue(all(
            state["status"] == "ready" and state["state_version"] == 2
            for state in final.values()
        ))
        final_events = _events(ledger, plan["run_id"])
        self.assertEqual(
            Counter(
                (unit_id, kind)
                for unit_id in targets
                for kind in ("selection_invalidated", "selection_ready")
            ),
            _event_kinds(final_events),
        )
        self.assertEqual(4, len(final_events))
        self.assertEqual(
            len(final_events), len({event["command_id"] for event in final_events}),
        )
        self.assertTrue(
            {event["event_id"] for event in partial_events}
            <= {event["event_id"] for event in final_events}
        )
        self.assertEqual((0, 0), _runtime_counts(ledger, plan["run_id"]))

    def test_legacy_refresh_cannot_ready_wave_pending_frontier(self) -> None:
        fixture = self._fixture()
        plan, ledger, targets = fixture["plan"], fixture["ledger"], fixture["targets"]
        inputs = _wave_inputs(self, fixture)

        with mock.patch.object(
            wave_coordinator,
            "refresh_single_scc_context",
            side_effect=RuntimeError("injected stop after wave invalidation"),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "injected stop after wave invalidation",
            ):
                wave_coordinator.prepare_next_context_frontier_wave(
                    plan["portfolio"], **inputs,
                )

        pending = _target_states(ledger, plan["run_id"], targets)
        self.assertTrue(all(
            state["status"] == "pending_retrieval"
            and state["state_version"] == 1
            for state in pending.values()
        ))
        before_events = _events(ledger, plan["run_id"])
        legacy_error = None
        try:
            refresh_single_scc_context(
                plan["portfolio"],
                portfolio_reference=_reference(plan, "portfolio"),
                context_bundle_reference=_reference(plan, "context_pages"),
                ledger=ledger,
                harness_root=self.harness,
                out_root=self.out_root,
                out_root_rel="target/run",
                unit_id=targets[0],
            )
        except ValueError as error:
            legacy_error = error

        after = _target_states(ledger, plan["run_id"], targets)[targets[0]]
        after_events = _events(ledger, plan["run_id"])
        self.assertEqual(
            "pending_retrieval",
            after["status"],
            "legacy refresh without wave binding consumed a wave-pending frontier",
        )
        self.assertEqual(
            [event["event_id"] for event in before_events],
            [event["event_id"] for event in after_events],
            "legacy refresh recorded a selection_ready event for wave-pending state",
        )
        self.assertIsNotNone(
            legacy_error, "wave-pending refresh must require the bound wave inputs",
        )
        self.assertRegex(str(legacy_error), r"wave.*binding.*required")
        self.assertEqual((0, 0), _runtime_counts(ledger, plan["run_id"]))

    def _fixture(self) -> dict:
        plan = self.plan(SOURCE)
        ledger = self.ledger()
        dag = self.load(_path(plan, "portfolio_dag"))
        context = self.load(_path(plan, "context_pages"))
        self.assertGreaterEqual(len(dag["waves"]), 3)
        previous = dag["waves"][0]["group_ids"]
        targets = dag["waves"][1]["group_ids"]
        self.assertEqual(2, len(targets))
        groups = {item["group_id"]: item for item in dag["groups"]}
        self.assertTrue(all(
            groups[unit_id]["dependencies"] == previous for unit_id in targets
        ))
        _mark_last_good(ledger, plan["run_id"], previous)
        return {
            "plan": plan,
            "ledger": ledger,
            "dag": dag,
            "context": context,
            "targets": targets,
        }


def _wave_inputs(case: ProjectMigrationControllerCase, fixture: dict) -> dict:
    plan = fixture["plan"]
    return {
        "portfolio_reference": _reference(plan, "portfolio"),
        "latest_dag": fixture["dag"],
        "latest_dag_reference": _reference(plan, "portfolio_dag"),
        "context_bundle": fixture["context"],
        "context_bundle_reference": _reference(plan, "context_pages"),
        "completed_wave_index": 0,
        "failure_evidence": [],
        "expansion_queries": [],
        "ledger": fixture["ledger"],
        "harness_root": case.harness,
        "out_root": case.out_root,
        "out_root_rel": "target/run",
    }


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


def _target_states(
    ledger: object, run_id: str, unit_ids: list[str],
) -> dict[str, dict]:
    wanted = set(unit_ids)
    return {
        item["unit_id"]: item for item in ledger.context_frontier_states(run_id)
        if item["unit_id"] in wanted
    }


def _events(ledger: object, run_id: str) -> list[dict]:
    with ledger.connect() as connection:
        rows = connection.execute(
            """select event_id,unit_id,command_kind,command_id
               from context_frontier_events where run_id=? order by event_id""",
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _event_kinds(events: list[dict]) -> Counter:
    return Counter((event["unit_id"], event["command_kind"]) for event in events)


def _runtime_counts(ledger: object, run_id: str) -> tuple[int, int]:
    with ledger.connect() as connection:
        attempts = connection.execute(
            "select count(*) from attempts where run_id=?", (run_id,),
        ).fetchone()[0]
        leases = connection.execute(
            "select count(*) from leases where run_id=?", (run_id,),
        ).fetchone()[0]
    return int(attempts), int(leases)


def _path(plan: dict, name: str) -> str:
    return f"target/run/{plan['artifacts'][name]['path']}"


def _reference(plan: dict, name: str) -> dict:
    return {**plan["artifacts"][name], "path": _path(plan, name)}


if __name__ == "__main__":
    unittest.main()
