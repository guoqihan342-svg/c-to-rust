from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from validation.tools._project_migration_harness.project_candidate_completion import (
    advance_gate_pending_candidates,
)


MODULE = (
    "validation.tools._project_migration_harness."
    "project_candidate_completion."
)
PASSED = {"schema_version": 1, "status": "passed"}


class ProjectCandidateCompletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = mock.Mock()
        connection = mock.MagicMock()
        self.ledger.connect.return_value = connection
        self.connection = connection.__enter__.return_value
        self.paths = {
            "out_root": Path("out"), "out_root_rel": "target/run",
            "quarantine_root": Path("quarantine"),
            "runtime_root": Path("runtime"), "timeout_seconds": 300,
        }

    def test_gate_pending_candidate_runs_every_gate_and_promotes(self) -> None:
        self.ledger.unit_states.side_effect = [
            [{"unit_id": "unit", "status": "gate-pending"}],
            [{"unit_id": "unit", "status": "last_good"}],
        ]
        self.ledger.bind_verification_candidate_set.return_value = "a" * 64
        manifest = {
            "roots": ["unit"],
            "members": [{
                "unit_id": "unit", "artifact_id": "candidate",
                "content_sha256": "b" * 64,
            }],
        }
        semantic = mock.Mock(return_value=PASSED)
        with (
            mock.patch(MODULE + "candidate_set_manifest", return_value=manifest),
            mock.patch(MODULE + "verify_candidate_compile", return_value=PASSED),
            mock.patch(MODULE + "semantic_runner", return_value=semantic) as selector,
            mock.patch(MODULE + "verify_candidate_final", return_value=PASSED),
            mock.patch(
                MODULE + "promote_current_verified_candidate",
                return_value={"status": "last-good"},
            ) as promote,
        ):
            result = advance_gate_pending_candidates(
                ledger=self.ledger, run_id="run", **self.paths,
            )

        self.assertEqual("advanced", result["status"])
        self.assertEqual(["oracle-replay-diff", "negative", "unsafe-alias", "abi-layout"], [
            call.args[0] for call in selector.call_args_list
        ])
        self.assertEqual(4, semantic.call_count)
        promote.assert_called_once()

    def test_candidate_ready_waits_for_existing_worker_pipeline(self) -> None:
        self.ledger.unit_states.return_value = [{
            "unit_id": "unit", "status": "candidate-ready",
        }]
        with mock.patch(MODULE + "verify_candidate_compile") as compile_runner:
            result = advance_gate_pending_candidates(
                ledger=self.ledger, run_id="run", **self.paths,
            )
        self.assertEqual("waiting", result["status"])
        self.assertEqual("candidate-worker-required", result["stage"])
        compile_runner.assert_not_called()

    def test_semantic_failure_returns_repair_required(self) -> None:
        self.ledger.unit_states.return_value = [{
            "unit_id": "unit", "status": "gate-pending",
        }]
        self.ledger.bind_verification_candidate_set.return_value = "a" * 64
        manifest = {
            "roots": ["unit"],
            "members": [{
                "unit_id": "unit", "artifact_id": "candidate",
                "content_sha256": "b" * 64,
            }],
        }
        failed = {"schema_version": 1, "status": "failed"}
        with (
            mock.patch(MODULE + "candidate_set_manifest", return_value=manifest),
            mock.patch(MODULE + "verify_candidate_compile", return_value=PASSED),
            mock.patch(MODULE + "semantic_runner", return_value=lambda **_: failed),
        ):
            result = advance_gate_pending_candidates(
                ledger=self.ledger, run_id="run", **self.paths,
            )
        self.assertEqual("repair-required", result["status"])
        self.assertEqual("candidate-wave-oracle-replay-diff", result["stage"])


if __name__ == "__main__":
    unittest.main()
