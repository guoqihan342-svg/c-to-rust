from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.project_candidate_domain import (
    candidate_verification_context,
)
from validation.tools._project_migration_harness.project_candidate_verification_receipt import (
    reopen_candidate_project_verification,
    validate_candidate_project_verification,
)
from validation.tools.project_migration_candidate_receipt_payload_test_support import (
    CandidateReceiptFixture,
)


class ProjectCandidateVerificationReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="candidate-receipt-")
        self.addCleanup(temporary.cleanup)
        self.fixture = CandidateReceiptFixture(Path(temporary.name))
        self.repo = self.fixture.repo
        self.ledger_path = self.fixture.ledger_path
        self.quarantine_root = self.fixture.quarantine_root
        self.candidate_set_sha256 = self.fixture.candidate_set_sha256
        self.payload = self.fixture.payload()

    def test_valid_receipt_reopens_raw_cargo_evidence(self) -> None:
        reopened = self._reopen(self.fixture.write(self.payload))
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

    def test_legacy_v1_receipt_cannot_regain_candidate_authority(self) -> None:
        legacy = copy.deepcopy(self.payload)
        legacy["schema_version"] = 1
        with self.assertRaisesRegex(ValueError, "identity_invalid"):
            validate_candidate_project_verification(legacy)

    def test_execution_envelope_is_recomputed_and_fail_closed(self) -> None:
        for field, value in (
            ("status", "unknown"),
            ("cargo_executed", False),
            ("semantic_gate", True),
        ):
            changed = copy.deepcopy(self.payload)
            changed["execution"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, "execution_invalid",
            ):
                validate_candidate_project_verification(changed)

    def test_native_cargo_and_fact_binding_tamper_fail_closed(self) -> None:
        variants = []
        native = copy.deepcopy(self.payload)
        native["native_link_settlement"]["binding_sha256"] = "0" * 64
        variants.append(native)
        cargo = copy.deepcopy(self.payload)
        cargo["cargo_observations"]["cargo-check"]["check"]["returncode"] = 9
        variants.append(cargo)
        facts = copy.deepcopy(self.payload)
        facts["cargo_fact_evidence"]["cargo_metadata"]["facts_sha256"] = "0" * 64
        variants.append(facts)
        for changed in variants:
            with self.assertRaises((ValueError, LedgerError)):
                validate_candidate_project_verification(changed)

    def test_raw_output_content_drift_blocks_deep_reopen(self) -> None:
        reference = self.fixture.write(self.payload)
        raw = self.payload["cargo_observations"]["cargo-test"]["check"][
            "stdout_ref"
        ]
        self._overwrite(raw, b"changed")
        with self.assertRaises(LedgerError):
            self._reopen(reference)

    def test_metadata_raw_fact_drift_blocks_deep_reopen(self) -> None:
        reference = self.fixture.write(self.payload)
        raw = self.payload["cargo_fact_evidence"]["cargo_metadata"]["source"]
        self._overwrite(raw, b"changed")
        with self.assertRaisesRegex(LedgerError, "Cargo fact evidence"):
            self._reopen(reference)

    def test_metadata_stderr_drift_blocks_deep_reopen(self) -> None:
        reference = self.fixture.write(self.payload)
        raw = self.payload["execution"]["fact_probes"]["cargo-metadata"][
            "stderr_ref"
        ]
        self._overwrite(raw, b"changed")
        with self.assertRaisesRegex(LedgerError, "Cargo fact evidence"):
            self._reopen(reference)

    def test_derived_fact_reference_size_is_rechecked_from_cas(self) -> None:
        changed = copy.deepcopy(self.payload)
        facts = changed["cargo_fact_evidence"]
        facts["cargo_metadata"]["evidence"]["size_bytes"] += 1
        core = {key: value for key, value in facts.items() if key != "binding_sha256"}
        facts["binding_sha256"] = content_sha256(core)
        changed["verification_context_sha256"] = candidate_verification_context(
            changed,
            changed["build_ir_verification"],
            changed["materialization"],
            changed["execution"],
            changed["cargo_observations"],
            changed["native_link_settlement"],
            facts,
        )
        validate_candidate_project_verification(changed)
        with self.assertRaisesRegex(LedgerError, "Cargo fact evidence"):
            self._reopen(self.fixture.write(changed))

    def test_quarantine_generation_drift_blocks_deep_reopen(self) -> None:
        reference = self.fixture.write(self.payload)
        (self.quarantine_root / "generations/current/Cargo.toml").write_text(
            "changed", encoding="utf-8",
        )
        with self.assertRaisesRegex(LedgerError, "generation"):
            self._reopen(reference)

    def test_expected_identity_mismatch_blocks_reopen(self) -> None:
        reference = self.fixture.write(self.payload)
        with self.assertRaisesRegex(LedgerError, "binding drifted"):
            self._reopen(reference, run_id="other-run")

    def _reopen(self, reference: dict, *, run_id: str = "receipt-run") -> dict:
        return reopen_candidate_project_verification(
            self.ledger_path,
            reference,
            quarantine_root=self.quarantine_root,
            run_id=run_id,
            candidate_set_sha256=self.candidate_set_sha256,
            rust_project_ir_sha256="a" * 64,
            rust_project_interface_sha256="b" * 64,
        )

    def _overwrite(self, reference: dict, data: bytes) -> None:
        target = self.repo.joinpath(*Path(reference["path"]).parts)
        target.chmod(0o600)
        target.write_bytes(data)


if __name__ == "__main__":
    unittest.main()
