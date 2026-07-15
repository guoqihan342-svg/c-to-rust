from __future__ import annotations

import copy
import hashlib
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from collections.abc import Iterator
from unittest import mock

from validation.tools._project_migration_harness.candidate_cargo_fact_binding import (
    reopen_candidate_cargo_fact_binding,
    reopen_candidate_cargo_fact_payloads,
)
from validation.tools._project_migration_harness.integration_generation import (
    recover_current_generation,
)
from validation.tools._project_migration_harness.project_candidate_verification_evidence import (
    bind_candidate_cargo_evidence,
)
from validation.tools._project_migration_harness.project_verification import (
    run_cargo_generation_gates,
)
from validation.tools._project_migration_harness.cargo_raw_output_evidence import (
    write_cargo_raw_output,
)
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxDiscovery,
)
from validation.tools.project_migration_cargo_fact_test_support import (
    CargoFactBackend,
)
from validation.tools.project_migration_sandbox_test_support import (
    managed_project,
    passing_probe_receipt,
)


class ProjectMigrationCandidateCargoFactBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="candidate-cargo-facts-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        project, self.cargo = managed_project(self.root)
        self.generation = recover_current_generation(project)
        self.assertIsNotNone(self.generation)
        self.out_root = self.root / "target/run"
        self.out_root.mkdir(parents=True)
        self.ledger_path = self.out_root / "state/project-migration.sqlite3"
        self.backend = CargoFactBackend()

    def test_runner_persistence_parser_and_deep_reopen_share_one_source(self) -> None:
        execution = self._run()
        persisted, checks, observations, statuses, facts = (
            bind_candidate_cargo_evidence(
                execution,
                native_required=False,
                out_root=self.out_root,
                out_root_rel="target/run",
            )
        )
        self.assertEqual(
            {"cargo-check": "passed", "cargo-test": "passed"}, statuses,
        )
        self.assertEqual("ready", facts["status"])
        self.assertGreater(facts["compiler_artifacts"]["artifact_count"], 0)
        self.assertNotIn(
            "_captured_stdout", persisted["fact_probes"]["cargo-metadata"],
        )
        self.assertEqual({"check", "test"}, set(checks))
        reopened = reopen_candidate_cargo_fact_binding(
            self.ledger_path, facts,
            execution=persisted,
            observations=observations,
        )
        self.assertEqual(facts, reopened)
        payloads = reopen_candidate_cargo_fact_payloads(
            self.ledger_path, facts,
            execution=persisted,
            observations=observations,
        )
        self.assertEqual(facts, payloads["binding"])
        self.assertEqual(
            facts["cargo_metadata"]["facts_sha256"],
            payloads["cargo_metadata"]["facts_sha256"],
        )
        self.assertEqual(
            facts["compiler_artifacts"]["artifact_set_sha256"],
            payloads["compiler_artifacts"]["artifact_set_sha256"],
        )

    def test_metadata_command_near_match_is_rejected_before_fact_binding(self) -> None:
        execution = copy.deepcopy(self._run())
        execution["fact_probes"]["cargo-metadata"]["command"].append("--verbose")
        with self.assertRaisesRegex(ValueError, "metadata_source_missing"):
            bind_candidate_cargo_evidence(
                execution,
                native_required=False,
                out_root=self.out_root,
                out_root_rel="target/run",
            )

    def test_failed_check_raw_outputs_are_persisted_before_fact_parse_blocks(self) -> None:
        self.backend = CargoFactBackend(fail_stage="check")
        execution = self._run()
        persisted, _, observations, statuses, facts = (
            bind_candidate_cargo_evidence(
                execution,
                native_required=False,
                out_root=self.out_root,
                out_root_rel="target/run",
            )
        )
        self.assertEqual("failed", statuses["cargo-check"])
        self.assertEqual("failed", statuses["cargo-test"])
        self.assertEqual("blocked", facts["status"])
        self.assertTrue(facts["raw_output_bound"])
        metadata = persisted["fact_probes"]["cargo-metadata"]
        cargo_check = observations["cargo-check"]["check"]
        for check in (metadata, cargo_check):
            for stream in ("stdout", "stderr"):
                reference = check[f"{stream}_ref"]
                self.assertIsInstance(reference, dict)
                self.assertTrue(
                    self.root.joinpath(*Path(reference["path"]).parts).is_file()
                )

    def test_metadata_cas_failure_reports_raw_output_as_unbound(self) -> None:
        execution = self._run()

        def fail_metadata(*args, **kwargs):
            if kwargs.get("gate_kind") == "cargo-metadata":
                raise OSError("injected metadata CAS failure")
            return write_cargo_raw_output(*args, **kwargs)

        with mock.patch(
            "validation.tools._project_migration_harness."
            "cargo_raw_output_evidence.write_cargo_raw_output",
            side_effect=fail_metadata,
        ):
            persisted, _, _, _, facts = bind_candidate_cargo_evidence(
                execution, native_required=False, out_root=self.out_root,
                out_root_rel="target/run",
            )
        self.assertEqual("blocked", persisted["status"])
        self.assertFalse(facts["raw_output_bound"])
        self.assertEqual(
            "candidate_cargo_raw_output_unavailable", facts["reason_code"],
        )
        probe = persisted["fact_probes"]["cargo-metadata"]
        self.assertIsNone(probe["stdout_ref"])
        self.assertIn(
            "cargo_raw_output_unavailable",
            {item["code"] for item in persisted["diagnostics"]},
        )

    def test_single_stream_hash_drift_reports_raw_output_as_unbound(self) -> None:
        execution = self._run()
        execution["fact_probes"]["cargo-metadata"]["_captured_stderr"] = b"drift"
        persisted, _, _, _, facts = bind_candidate_cargo_evidence(
            execution, native_required=False, out_root=self.out_root,
            out_root_rel="target/run",
        )
        self.assertEqual("blocked", persisted["status"])
        self.assertFalse(facts["raw_output_bound"])
        self.assertIsNone(
            persisted["fact_probes"]["cargo-metadata"]["stderr_ref"]
        )

    def test_native_trace_blocker_returns_bound_raw_outputs_without_ready_facts(self) -> None:
        execution = self._run()
        blocked = copy.deepcopy(execution)
        blocked["status"] = "blocked"
        blocked["diagnostics"].append({
            "code": "native_link_trace_invalid",
            "stage": "native-link-trace",
            "message": "injected trace blocker",
        })
        blocked["native_link_trace"] = {
            "schema_version": 1, "status": "blocked", "cargo_gate": None,
            "source_stdout_sha256": None,
            "native_linker_binding_sha256": None, "artifact": None,
            "entry_count": 0, "semantic_gate": False,
        }
        with mock.patch(
            "validation.tools._project_migration_harness."
            "project_candidate_verification_evidence."
            "persist_captured_native_link_trace",
            return_value=blocked,
        ):
            persisted, _, _, _, facts = bind_candidate_cargo_evidence(
                execution, native_required=True, out_root=self.out_root,
                out_root_rel="target/run",
            )
        self.assertEqual("blocked", persisted["status"])
        self.assertTrue(facts["raw_output_bound"])
        self.assertEqual(
            "candidate_native_link_trace_blocked", facts["reason_code"],
        )
        self.assertIn(
            "native_link_trace_invalid",
            {item["code"] for item in persisted["diagnostics"]},
        )

    def test_invalid_metadata_json_preserves_bound_raw_evidence(self) -> None:
        execution = self._run()
        invalid = b"{not-json"
        probe = execution["fact_probes"]["cargo-metadata"]
        probe["_captured_stdout"] = invalid
        probe["stdout_sha256"] = hashlib.sha256(invalid).hexdigest()
        persisted, _, _, _, facts = bind_candidate_cargo_evidence(
            execution, native_required=False, out_root=self.out_root,
            out_root_rel="target/run",
        )
        self.assertEqual("passed", persisted["status"])
        self.assertEqual("blocked", facts["status"])
        self.assertTrue(facts["raw_output_bound"])
        self.assertEqual(
            "candidate_cargo_fact_derivation_failed", facts["reason_code"],
        )
        reference = persisted["fact_probes"]["cargo-metadata"]["stdout_ref"]
        self.assertTrue(
            self.root.joinpath(*Path(reference["path"]).parts).is_file()
        )

    def _run(self) -> dict:
        with self._sandbox():
            return run_cargo_generation_gates(
                self.generation,
                runtime_root=self.root / "runtime",
                timeout_seconds=60,
                capture_raw_output=True,
                capture_cargo_facts=True,
            )

    @contextmanager
    def _sandbox(self) -> Iterator[None]:
        with (
            mock.patch(
                "validation.tools._project_migration_harness."
                "project_verification._cargo_binary",
                return_value=self.cargo,
            ),
            mock.patch(
                "validation.tools._project_migration_harness."
                "project_verification.discover_sandbox_backend",
                return_value=SandboxDiscovery(
                    self.backend,
                    None,
                    passing_probe_receipt(self.backend.contract),
                ),
            ),
        ):
            yield


if __name__ == "__main__":
    unittest.main()
