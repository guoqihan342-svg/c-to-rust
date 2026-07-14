from __future__ import annotations

from pathlib import Path, PurePosixPath
import unittest
from unittest import mock

from validation.tools._project_migration_harness import controller_runtime
from validation.tools._project_migration_harness.controller import (
    run_and_ingest_opencode_worker,
)
from validation.tools.project_migration_runtime_test_support import (
    LOGICAL_MODEL,
    RESOLVED_MODEL,
    RuntimeHarnessCase,
)
from validation.tools.test_project_migration_context_frontier_refresh import (
    _invalidate_frontier,
    _materialize_initial_context,
    _refresh,
)


class ProjectMigrationContextFrontierRuntimeOverlayDriftTests(
    RuntimeHarnessCase,
):
    maxDiff = None

    def test_overlay_drift_is_prelaunch_blocked_without_runtime_leak(self) -> None:
        self._assert_prelaunch_drift_contract("overlay")

    def test_refresh_cas_drift_is_prelaunch_blocked_without_runtime_leak(self) -> None:
        self._assert_prelaunch_drift_contract("refresh_cas")

    def test_page_drift_is_prelaunch_blocked_without_runtime_leak(self) -> None:
        self._assert_prelaunch_drift_contract("page")

    def test_catalog_drift_is_prelaunch_blocked_without_runtime_leak(self) -> None:
        self._assert_prelaunch_drift_contract("catalog")

    def _assert_prelaunch_drift_contract(self, artifact: str) -> None:
        plan = self.plan()
        ledger = self.ledger()
        _materialize_initial_context(plan, ledger, self)
        current = ledger.context_frontier_states(plan["run_id"])[0]
        _invalidate_frontier(ledger, current, f"runtime-{artifact}")
        refreshed = _refresh(plan, ledger, self)
        launch = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(launch["request"])
        preflight = self.preflight(plan["run_id"])
        reference = _drift_reference(artifact, refreshed, request)
        _absolute(self.harness, reference).write_bytes(b"{}\n")

        result: dict | None = None
        raised: str | None = None
        original_runner = controller_runtime.subprocess_runner_with_environment
        with (
            mock.patch.object(
                controller_runtime,
                "subprocess_runner_with_environment",
                wraps=original_runner,
            ) as provider,
            mock.patch(
                "validation.tools._ai_candidate_harness_parts.provider_process."
                "subprocess.Popen",
                side_effect=OSError("test blocked process creation"),
            ) as process,
        ):
            try:
                result = run_and_ingest_opencode_worker(
                    launch["request"],
                    preflight,
                    ledger=ledger,
                    harness_root=self.harness,
                    logical_model=LOGICAL_MODEL,
                    resolved_model=RESOLVED_MODEL,
                )
            except Exception as error:  # Captured so leak state remains observable.
                raised = f"{type(error).__name__}: {error}"

        runtime = _runtime_state(ledger, plan["run_id"])
        observed = {
            "status": result.get("status") if result is not None else None,
            "attempt_consumed": (
                result.get("attempt_consumed") if result is not None else None
            ),
            "raised": raised,
            "provider_calls": provider.call_count,
            "subprocess_calls": process.call_count,
            **runtime,
        }
        self.assertEqual({
            "status": "prelaunch-blocked",
            "attempt_consumed": False,
            "raised": None,
            "provider_calls": 0,
            "subprocess_calls": 0,
            "attempt_statuses": ["cancelled"],
            "lease_statuses": ["released"],
            "running_attempts": 0,
            "active_leases": 0,
        }, observed)


def _drift_reference(artifact: str, refreshed: dict, request: dict) -> dict:
    if artifact == "overlay":
        return refreshed["context_overlay"]
    if artifact == "refresh_cas":
        return refreshed["refresh_input"]
    if artifact == "catalog":
        return request["context"]["catalog"]
    if artifact == "page":
        return request["context"]["pages"][0]
    raise AssertionError(f"unknown drift artifact: {artifact}")


def _absolute(root: Path, reference: dict) -> Path:
    return root.joinpath(*PurePosixPath(reference["path"]).parts)


def _runtime_state(ledger: object, run_id: str) -> dict:
    with ledger.connect() as connection:
        attempt_statuses = [
            str(row["status"])
            for row in connection.execute(
                "select status from attempts where run_id=? order by attempt_id",
                (run_id,),
            )
        ]
        lease_statuses = [
            str(row["status"])
            for row in connection.execute(
                "select status from leases where run_id=? order by unit_id",
                (run_id,),
            )
        ]
    return {
        "attempt_statuses": attempt_statuses,
        "lease_statuses": lease_statuses,
        "running_attempts": attempt_statuses.count("running"),
        "active_leases": lease_statuses.count("active"),
    }


if __name__ == "__main__":
    unittest.main()
