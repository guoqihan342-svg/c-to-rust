from __future__ import annotations

import json
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


class ProjectRepairResponseContractTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-repair-response-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out = self.root / "target/run"
        source = (
            Path(__file__).resolve().parents[2]
            / ".opencode/agents/c2rust-candidate.md"
        )
        target = self.root / ".opencode/agents/c2rust-candidate.md"
        target.parent.mkdir(parents=True)
        target.write_bytes(source.read_bytes())
        self.ledger = ProjectLedger(self.out / "state/project-migration.sqlite3")

    def test_invalid_model_json_is_a_known_retryable_result(self) -> None:
        _, request_ref, _, _ = materialized_repair_case(
            self.root, self.out, self.ledger, "invalid-model-json",
        )
        event = {
            "type": "text", "text": "not-a-json-object",
            "sessionID": "session-invalid-model-json",
        }
        execution = ProviderExecution(
            0, json.dumps(event) + "\n", "",
            identity_receipt=self.identity("session-invalid-model-json"),
        )

        result = self.run_runtime(request_ref, execution)

        self.assertEqual("retry-ready", result["status"])
        self.assertEqual("provider_response_contract_failed", result["root_cause_key"])
        self.assertTrue(result["model_launched"])
        self.assertEqual("recovered", self.attempt_status(result["attempt_id"]))

    def test_oversized_model_output_is_redacted_and_retryable(self) -> None:
        _, request_ref, _, _ = materialized_repair_case(
            self.root, self.out, self.ledger, "oversized-model-output",
        )
        execution = ProviderExecution(0, "x" * 2_000_001, "")

        result = self.run_runtime(request_ref, execution)

        self.assertEqual("retry-ready", result["status"])
        self.assertEqual("provider_output_too_large", result["root_cause_key"])
        raw = self.root / Path(*result["artifacts"]["raw_response"]["path"].split("/"))
        self.assertLess(raw.stat().st_size, 1_000)
        self.assertIn("provider_output_redacted", raw.read_text(encoding="utf-8"))

    def run_runtime(self, request_ref: dict, execution: ProviderExecution) -> dict:
        with mock.patch(
            "validation.tools._project_migration_harness.project_repair_runtime."
            "subprocess_runner_with_environment",
            return_value=execution,
        ):
            return run_and_ingest_opencode_project_repair(
                request_ref, self.preflight(), ledger=self.ledger,
                harness_root=self.root, out_root=self.out,
                out_root_rel="target/run", logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )

    def preflight(self) -> dict:
        with mock.patch(
            "validation.tools._project_migration_harness.project_preflight_runner."
            "subprocess_runner_with_environment",
            return_value=ProviderExecution(0, f"{RESOLVED_MODEL}\n", ""),
        ):
            return run_project_worker_preflight(
                harness_root=self.root, out_root_rel="target/preflight",
                run_id="run", logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )["report"]

    def attempt_status(self, attempt_id: str) -> str:
        with self.ledger.connect() as connection:
            row = connection.execute(
                "select status from project_repair_attempts where attempt_id=?",
                (attempt_id,),
            ).fetchone()
        return str(row["status"])

    @staticmethod
    def identity(session_id: str) -> dict[str, str]:
        return {
            "source": "runner-contract", "session_id": session_id,
            "provider_id": "opencode", "model_id": "deepseek-v4-flash-free",
            "agent": "c2rust-candidate", "variant": "max",
            "opencode_version": "test-double",
        }


if __name__ == "__main__":
    unittest.main()
