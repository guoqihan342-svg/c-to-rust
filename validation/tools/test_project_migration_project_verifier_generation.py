from __future__ import annotations

import json
import shutil
import unittest
from unittest import mock

from validation.tools._ai_candidate_harness_parts.provider_runtime import (
    ProviderExecution,
)
from validation.tools._project_migration_harness.controller import (
    run_and_ingest_opencode_project_repair,
)
from validation.tools._project_migration_harness.integration_generation import (
    generation_store_root,
)
from validation.tools._project_migration_harness.ledger import LedgerError
from validation.tools._project_migration_harness.project_generation_context import (
    managed_project_root,
)
from validation.tools.project_migration_gate_authority_test_support import (
    ProjectMigrationGateAuthorityCase,
)
from validation.tools.project_migration_project_verifier_repair_test_support import (
    ProjectVerifierRepairFlowSupportMixin,
)


class ProjectVerifierGenerationTests(
    ProjectVerifierRepairFlowSupportMixin, ProjectMigrationGateAuthorityCase,
):
    def setUp(self) -> None:
        super().setUp()
        self._prepare_verifier_case()

    def test_dispatch_rejects_missing_bound_source_generation(self) -> None:
        self._remove_current_generation()
        with self.assertRaisesRegex(LedgerError, "source generation"):
            self._candidate()
        self.assertEqual(0, self.ledger.project_repair_budget(
            run_id="run",
        ).provider_calls)

    def test_runtime_rechecks_generation_before_provider_launch(self) -> None:
        _receipt, request, request_ref, _base_ref, preflight = (
            self._materialized_request()
        )
        self._remove_current_generation()
        provider = mock.Mock(side_effect=AssertionError("provider must not launch"))
        with mock.patch(
            "validation.tools._project_migration_harness.project_repair_runtime."
            "subprocess_runner_with_environment",
            provider,
        ):
            result = run_and_ingest_opencode_project_repair(
                request_ref, preflight, ledger=self.ledger,
                harness_root=self.harness, out_root=self.out_root,
                out_root_rel="target/run", logical_model="DeepSeek-V4-Flash",
                resolved_model="opencode/deepseek-v4-flash-free",
            )
        self.assertEqual("retry-ready", result["status"])
        self.assertEqual("project-repair-source-generation-drift", result["stage"])
        self.assertFalse(result["model_launched"])
        provider.assert_not_called()
        projection = self.ledger.project_repair_projection(
            run_id="run", queue_sha256=request["project_repair_queue_sha256"],
            repair_id=request["repair_id"],
        )
        self.assertEqual("retry-ready", projection.status)
        self.assertEqual(0, self.ledger.project_repair_budget(
            run_id="run",
        ).provider_calls)

    def test_runtime_recovers_corrupt_generation_pointer_without_provider(self) -> None:
        _receipt, request, request_ref, _base_ref, preflight = (
            self._materialized_request()
        )
        project_root = managed_project_root(self.out_root)
        (generation_store_root(project_root) / "CURRENT").write_text(
            "{}", encoding="ascii",
        )
        provider = mock.Mock(side_effect=AssertionError("provider must not launch"))
        with mock.patch(
            "validation.tools._project_migration_harness.project_repair_runtime."
            "subprocess_runner_with_environment",
            provider,
        ):
            result = run_and_ingest_opencode_project_repair(
                request_ref, preflight, ledger=self.ledger,
                harness_root=self.harness, out_root=self.out_root,
                out_root_rel="target/run", logical_model="DeepSeek-V4-Flash",
                resolved_model="opencode/deepseek-v4-flash-free",
            )
        self.assertEqual("retry-ready", result["status"])
        self.assertFalse(result["model_launched"])
        provider.assert_not_called()
        projection = self.ledger.project_repair_projection(
            run_id="run", queue_sha256=request["project_repair_queue_sha256"],
            repair_id=request["repair_id"],
        )
        self.assertEqual("retry-ready", projection.status)
        self.assertEqual(0, self.ledger.project_repair_budget(
            run_id="run",
        ).provider_calls)

    def test_runtime_launches_once_then_waits_for_revalidation(self) -> None:
        _receipt, request, request_ref, _base_ref, preflight = (
            self._materialized_request()
        )
        calls = []

        def provider(argv, _timeout, **_kwargs):
            calls.append(argv)
            event = {
                "type": "text", "text": json.dumps(self._response(request)),
                "sessionID": "session-project-verifier-repair",
            }
            return ProviderExecution(
                0, json.dumps(event) + "\n", "",
                identity_receipt={
                    "source": "runner-contract",
                    "session_id": "session-project-verifier-repair",
                    "provider_id": "opencode",
                    "model_id": "deepseek-v4-flash-free",
                    "agent": "c2rust-candidate", "variant": "max",
                    "opencode_version": "test-double",
                },
            )

        with mock.patch(
            "validation.tools._project_migration_harness.project_repair_runtime."
            "subprocess_runner_with_environment",
            side_effect=provider,
        ):
            result = run_and_ingest_opencode_project_repair(
                request_ref, preflight, ledger=self.ledger,
                harness_root=self.harness, out_root=self.out_root,
                out_root_rel="target/run", logical_model="DeepSeek-V4-Flash",
                resolved_model="opencode/deepseek-v4-flash-free",
            )
        self.assertEqual("pending-reverification", result["status"])
        self.assertEqual("candidate-ready", result["ledger"]["ledger_status"])
        self.assertEqual(1, len(calls))
        self.assertEqual(1, self.ledger.project_repair_budget(
            run_id="run",
        ).provider_calls)

    def _remove_current_generation(self) -> None:
        project_root = managed_project_root(self.out_root)
        shutil.rmtree(project_root)
        (generation_store_root(project_root) / "CURRENT").unlink()


if __name__ == "__main__":
    unittest.main()
