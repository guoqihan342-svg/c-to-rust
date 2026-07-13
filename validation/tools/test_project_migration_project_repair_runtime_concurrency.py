from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools._ai_candidate_harness_parts.provider_runtime import (
    ProviderExecution,
)
from validation.tools._project_migration_harness.controller import (
    run_and_ingest_opencode_project_repair,
)
from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.project_preflight_runner import (
    run_project_worker_preflight,
)
from validation.tools.project_migration_project_repair_test_support import (
    materialized_repair_case,
)
from validation.tools.project_migration_runtime_test_support import (
    LOGICAL_MODEL,
    RESOLVED_MODEL,
)


class ProjectRepairRuntimeConcurrencyTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-repair-runtime-race-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out = self.root / "target/run"
        agent_source = (
            Path(__file__).resolve().parents[2]
            / ".opencode/agents/c2rust-candidate.md"
        )
        agent_target = self.root / ".opencode/agents/c2rust-candidate.md"
        agent_target.parent.mkdir(parents=True)
        agent_target.write_bytes(agent_source.read_bytes())
        self.ledger = ProjectLedger(self.out / "state/project-migration.sqlite3")

    def test_duplicate_runtime_cannot_launch_an_already_claimed_attempt(self) -> None:
        request, request_ref, _, _ = materialized_repair_case(
            self.root, self.out, self.ledger, "runtime-duplicate-launch",
        )
        binding = request["execution_binding"]
        self.assertTrue(self.ledger.mark_project_repair_command_started(
            attempt_id=binding["attempt_id"], worker_id=request["worker_id"],
            expected_version=binding["fencing_token"],
        ))
        with mock.patch(
            "validation.tools._project_migration_harness.project_repair_runtime."
            "subprocess_runner_with_environment",
        ) as provider:
            result = run_and_ingest_opencode_project_repair(
                request_ref, self.preflight(), ledger=self.ledger,
                harness_root=self.root, out_root=self.out,
                out_root_rel="target/run", logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )
        self.assertEqual("waiting", result["status"])
        self.assertEqual(
            "project-repair-launch-already-claimed", result["stage"],
        )
        self.assertFalse(result["model_launched"])
        provider.assert_not_called()
        projection = self.ledger.project_repair_projection(
            run_id="run", queue_sha256=request["project_repair_queue_sha256"],
            repair_id=request["repair_id"],
        )
        self.assertEqual("running", projection.status)

    def preflight(self) -> dict:
        with mock.patch(
            "validation.tools._project_migration_harness.project_preflight_runner."
            "subprocess_runner_with_environment",
            return_value=ProviderExecution(0, f"{RESOLVED_MODEL}\n", ""),
        ):
            generated = run_project_worker_preflight(
                harness_root=self.root, out_root_rel="target/preflight",
                run_id="run", logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )
        return generated["report"]


if __name__ == "__main__":
    unittest.main()
