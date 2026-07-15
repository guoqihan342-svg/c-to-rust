from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.cargo_raw_output_evidence import (
    write_cargo_raw_output,
)
from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.project_candidate_domain import (
    candidate_domain_context_sha256,
    candidate_verification_context,
)
from validation.tools._project_migration_harness.project_candidate_verification_receipt import (
    reopen_candidate_project_verification,
    validate_candidate_project_verification,
)
from validation.tools._project_migration_harness.project_cargo_evidence import (
    CARGO_COMMANDS,
    project_cargo_observation,
)
from validation.tools._project_migration_harness.project_native_link_settlement_binding import (
    project_native_link_settlement_status,
)
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract,
    canonical_sha256,
)
from validation.tools._project_migration_harness.sandbox_requirements import (
    cargo_verification_plan,
)
from validation.tools.project_migration_sandbox_test_support import (
    passing_probe_receipt,
)


class ProjectCandidateVerificationReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="candidate-receipt-")
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        self.out_root = self.repo / "target/run"
        self.out_root.mkdir(parents=True)
        self.ledger_path = self.out_root / "state/project-migration.sqlite3"
        self.payload = self._payload()

    def test_valid_receipt_reopens_raw_cargo_evidence(self) -> None:
        reference = self._write(self.payload)
        reopened = reopen_candidate_project_verification(
            self.ledger_path,
            reference,
            run_id="receipt-run",
            candidate_set_sha256="c" * 64,
            rust_project_ir_sha256="a" * 64,
            rust_project_interface_sha256="b" * 64,
        )
        self.assertEqual("candidate-verified", reopened["status"])
        self.assertTrue(reopened["claim_boundary"]["candidate_project_gate"])
        self.assertFalse(reopened["claim_boundary"]["final_project_gate"])

    def test_status_claim_domain_and_verification_context_are_recomputed(self) -> None:
        variants = []
        for label, mutate in (
            ("status", lambda value: value.__setitem__("status", "failed")),
            ("claim", lambda value: value["claim_boundary"].__setitem__(
                "final_project_gate", True
            )),
            ("domain", lambda value: value.__setitem__(
                "candidate_set_sha256", "0" * 64
            )),
            ("context", lambda value: value.__setitem__(
                "verification_context_sha256", "0" * 64
            )),
            ("material", lambda value: value["materialization"].__setitem__(
                "last_good_updated", True
            )),
        ):
            changed = copy.deepcopy(self.payload)
            mutate(changed)
            variants.append((label, changed))
        for label, changed in variants:
            with self.subTest(label=label), self.assertRaises(ValueError):
                validate_candidate_project_verification(changed)

    def test_native_binding_and_cargo_observation_tamper_fail_closed(self) -> None:
        native = copy.deepcopy(self.payload)
        native["native_link_settlement"]["binding_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            validate_candidate_project_verification(native)

        cargo = copy.deepcopy(self.payload)
        cargo["cargo_observations"]["cargo-check"]["check"]["returncode"] = 9
        with self.assertRaises((ValueError, LedgerError)):
            validate_candidate_project_verification(cargo)

    def test_raw_output_content_drift_blocks_deep_reopen(self) -> None:
        reference = self._write(self.payload)
        raw = self.payload["cargo_observations"]["cargo-test"]["check"][
            "stdout_ref"
        ]
        target = self.repo.joinpath(*Path(raw["path"]).parts)
        target.chmod(0o600)
        target.write_bytes(b"changed")
        with self.assertRaises(LedgerError):
            reopen_candidate_project_verification(
                self.ledger_path,
                reference,
                run_id="receipt-run",
                candidate_set_sha256="c" * 64,
                rust_project_ir_sha256="a" * 64,
                rust_project_interface_sha256="b" * 64,
            )

    def test_expected_identity_mismatch_blocks_reopen(self) -> None:
        reference = self._write(self.payload)
        with self.assertRaisesRegex(LedgerError, "binding drifted"):
            reopen_candidate_project_verification(
                self.ledger_path,
                reference,
                run_id="other-run",
                candidate_set_sha256="c" * 64,
                rust_project_ir_sha256="a" * 64,
                rust_project_interface_sha256="b" * 64,
            )

    def _payload(self) -> dict:
        observations = self._observations()
        native = project_native_link_settlement_status("not-required")
        domain = {
            "run_id": "receipt-run",
            "run_context_sha256": "1" * 64,
            "dag_sha256": "2" * 64,
            "integration_manifest": {
                "path": "plan/integration-manifest.json",
                "sha256": "3" * 64,
                "size_bytes": 1,
            },
            "candidate_set_sha256": "c" * 64,
            "candidate_set_manifest_sha256": "4" * 64,
            "rust_project_ir_sha256": "a" * 64,
            "rust_project_interface_sha256": "b" * 64,
            "rust_project_binding_sha256": "5" * 64,
        }
        domain["candidate_domain_context_sha256"] = (
            candidate_domain_context_sha256(domain)
        )
        build_ir = {"schema_version": 1, "status": "verified", "blockers": []}
        materialization = {
            "status": "materialized",
            "candidate_set": {"sha256": "c" * 64, "member_count": 2},
            "rust_project_ir_sha256": "a" * 64,
            "rust_project_interface_sha256": "b" * 64,
            "rust_project_ir_scope": "full-project",
            "generation": {
                "path": "generations/current", "sha256": "6" * 64,
                "immutable": True,
            },
            "generation_manifest_ref": {
                "path": "generations/current/last-good-manifest.json",
                "sha256": "6" * 64, "size_bytes": 1,
            },
            "immutable": True,
            "last_good_updated": False,
            "cargo_executed": False,
        }
        execution = {
            "status": "passed", "cargo_executed": True,
            "project_input_sha256": "7" * 64,
        }
        payload = {
            "schema_version": 1,
            "artifact_kind": "candidate-project-verification",
            "status": "candidate-verified",
            **domain,
            "build_ir_verification": build_ir,
            "materialization": materialization,
            "execution": execution,
            "cargo_observations": observations,
            "cargo_statuses": {"cargo-check": "passed", "cargo-test": "passed"},
            "native_link_settlement": native,
            "state_effects": {
                "final_current_updated": False,
                "project_gate_records_written": 0,
                "candidate_only": True,
            },
            "claim_boundary": {
                "candidate_project_gate": True,
                "final_project_gate": False,
                "updates_final_current": False,
                "writes_project_gate_records": False,
                "semantic_gate": False,
                "semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
        }
        payload["verification_context_sha256"] = candidate_verification_context(
            domain, build_ir, materialization, execution, observations, native,
        )
        return payload

    def _observations(self) -> dict[str, dict]:
        contract = SandboxContract(
            backend="bubblewrap-v1",
            launcher_sha256="8" * 64,
            toolchain_sha256="9" * 64,
        )
        probe = passing_probe_receipt(contract)
        sandbox = {
            "contract": contract.payload(),
            "contract_sha256": contract.sha256,
            "probe_receipt": probe.payload(),
            "probe_receipt_sha256": probe.sha256,
            "cleanup_verified": True,
        }
        result = {}
        for index, gate in enumerate(("cargo-check", "cargo-test"), start=1):
            command = CARGO_COMMANDS[gate]
            plan = cargo_verification_plan(
                gate, tuple(command), "7" * 64,
                requirements=contract.requirements,
            )
            stdout = bytes([index])
            stderr = bytes([index + 2])
            check = {
                "command": command, "status": "passed", "cargo_executed": True,
                "returncode": 0, "timed_out": False,
                "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
                "stdout_ref": write_cargo_raw_output(
                    self.out_root, "target/run", gate_kind=gate,
                    stream="stdout", data=stdout,
                ),
                "stderr_ref": write_cargo_raw_output(
                    self.out_root, "target/run", gate_kind=gate,
                    stream="stderr", data=stderr,
                ),
                "sandbox_contract_sha256": contract.sha256,
                "sandbox_command_sha256": canonical_sha256(command),
                "sandbox_command_started": True,
                "sandbox_launcher_argv_sha256": "a" * 64,
                "sandbox_requirements_sha256": contract.requirements.sha256,
                "sandbox_verification_plan": plan.payload(),
                "sandbox_verification_plan_sha256": plan.sha256,
                "sandbox_probe_receipt_sha256": probe.sha256,
            }
            execution = {
                "project_input_sha256": "7" * 64,
                "project_state_before": "7" * 64,
                "project_state_after": "7" * 64,
                "project_state_unchanged": True,
                "sandbox": sandbox,
            }
            result[gate] = project_cargo_observation(
                execution, check, gate_kind=gate,
                expected_input_sha256="7" * 64,
            )
        return result

    def _write(self, payload: dict) -> dict:
        reference = write_content_addressed_json(
            self.out_root, "candidate-project-verification", payload,
        )
        return {**reference, "path": f"target/run/{reference['path']}"}


if __name__ == "__main__":
    unittest.main()
