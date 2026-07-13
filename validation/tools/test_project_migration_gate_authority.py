from __future__ import annotations

import sqlite3
from pathlib import Path
import unittest

from validation.tools._project_migration_harness.controller_gates import (
    record_candidate_gate,
)
from validation.tools._project_migration_harness.gate_authority import (
    CANDIDATE_REQUIRED_GATES,
    candidate_authority,
    candidate_verdict_payload,
)
from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)
from validation.tools._project_migration_harness.ledger import (
    LedgerError,
    ProjectLedger,
    SchemaVersionError,
)
from validation.tools.project_migration_gate_authority_test_support import (
    ProjectMigrationGateAuthorityCase,
)


class ProjectMigrationGateAuthorityTests(ProjectMigrationGateAuthorityCase):
    def test_identical_host_verifier_record_replay_is_idempotent(self) -> None:
        self.record_candidate_host_gate("compile", "passed", "same-record")
        self.record_candidate_host_gate("compile", "passed", "same-record")
        with self.ledger.connect() as connection:
            count = connection.execute(
                "select count(*) from verifier_records where record_id='same-record'"
            ).fetchone()[0]
        self.assertEqual(1, count)

    def test_cli_candidate_pass_is_denied_and_failure_uses_fixed_identity(self) -> None:
        with self.assertRaisesRegex(LedgerError, "cannot grant a pass"):
            record_candidate_gate(
                ledger=self.ledger,
                out_root=self.out_root,
                out_root_rel="target/run",
                run_id="run",
                unit_id="unit",
                candidate_artifact_id=self.candidate_id,
                record_id="claimed-pass",
                kind="verifier",
                gate_family="compile",
                status="passed",
                verifier_id="caller-controlled",
                diagnostics=[],
            )
        candidate_set = self.ledger.bind_verification_candidate_set(run_id="run")
        payload = candidate_verdict_payload(
            run_id="run",
            unit_id="unit",
            candidate_artifact_id=self.candidate_id,
            candidate_sha256=self.candidate_sha,
            gate_family="compile",
            status="passed",
            diagnostics=[],
            candidate_set_sha256=candidate_set,
            source_evidence=self.candidate_sources("compile", "passed", candidate_set),
        )
        reference = write_content_addressed_json(
            self.out_root, "candidate/compile", payload
        )
        with self.assertRaisesRegex(LedgerError, "identity is fixed"):
            self.ledger._record_derived_verification(
                record_id="wrong-authority",
                run_id="run",
                unit_id="unit",
                candidate_artifact_id=self.candidate_id,
                kind="verifier",
                status="passed",
                verifier_id="caller-controlled",
                evidence_path=f"target/run/{reference['path']}",
                evidence_sha256=str(reference["sha256"]),
                gate_family="compile",
            )
        result = record_candidate_gate(
            ledger=self.ledger,
            out_root=self.out_root,
            out_root_rel="target/run",
            run_id="run",
            unit_id="unit",
            candidate_artifact_id=self.candidate_id,
            record_id="observed-failure",
            kind="verifier",
            gate_family="compile",
            status="failed",
            verifier_id="caller-controlled",
            diagnostics=[{"code": "compile-failed", "stage": "compile"}],
        )
        self.assertEqual("failed", result["gate_status"])
        self.assertEqual(candidate_authority("compile"), result["authority_id"])
        with self.ledger.connect() as connection:
            row = connection.execute(
                "select status,verifier_id,gate_epoch,evidence_path from verifier_records"
            ).fetchone()
        self.assertEqual(("failed", candidate_authority("compile"), 1), tuple(row[:3]))
        self.assertTrue(str(row["evidence_path"]).endswith(f"/{result['evidence']['sha256']}.json"))

    def test_duplicate_record_is_non_overwriting_and_latest_failure_invalidates_pass(self) -> None:
        first = self.record_candidate_host_gate("compile", "passed", "compile-pass")
        old_path = self.harness.joinpath(*Path(first["path"]).parts)
        old_bytes = old_path.read_bytes()
        with self.assertRaisesRegex(LedgerError, "replay changed its binding"):
            self.record_candidate_host_gate("compile", "failed", "compile-pass")
        self.assertEqual(old_bytes, old_path.read_bytes())
        records = {"compile": "compile-pass"}
        for family in sorted(CANDIDATE_REQUIRED_GATES - {"compile"}):
            record_id = f"{family}-pass"
            self.record_candidate_host_gate(family, "passed", record_id)
            records[family] = record_id
        self.record_candidate_host_gate("final-verification", "passed", "candidate-final")
        self.record_candidate_host_gate("compile", "failed", "compile-failed-later")
        with self.assertRaisesRegex(LedgerError, "fresh final|latest candidate gate"):
            self.ledger.promote_last_good_from_verification(
                run_id="run",
                unit_id="unit",
                candidate_artifact_id=self.candidate_id,
                verifier_record_id=records["compile"],
                gate_record_id="candidate-final",
            )
        with self.ledger.connect() as connection:
            epochs = connection.execute(
                """select gate_epoch,status from verifier_records
                   where gate_family='compile' order by gate_epoch"""
            ).fetchall()
        self.assertEqual([(1, "passed"), (2, "failed")], [tuple(row) for row in epochs])

    def test_verification_candidate_set_stales_when_latest_candidate_changes(self) -> None:
        first_set = self.ledger.bind_verification_candidate_set(run_id="run")
        with self.assertRaisesRegex(LedgerError, "last-good"):
            self.ledger.bind_current_candidate_set(run_id="run")
        second_id, second_sha = self.make_candidate("candidate-two")
        self.candidate_id, self.candidate_sha = second_id, second_sha
        second_set = self.ledger.bind_verification_candidate_set(run_id="run")
        self.assertNotEqual(first_set, second_set)
        payload = candidate_verdict_payload(
            run_id="run", unit_id="unit",
            candidate_artifact_id=second_id,
            candidate_sha256=second_sha,
            gate_family="compile", status="passed", diagnostics=[],
            candidate_set_sha256=first_set,
            source_evidence=self.candidate_sources("compile", "passed", first_set),
        )
        reference = write_content_addressed_json(
            self.out_root, "candidate/compile", payload
        )
        with self.assertRaisesRegex(LedgerError, "current verification candidate set"):
            self.ledger._record_derived_verification(
                record_id="stale-cohort", run_id="run", unit_id="unit",
                candidate_artifact_id=second_id, kind="verifier", status="passed",
                verifier_id=candidate_authority("compile"),
                evidence_path=f"target/run/{reference['path']}",
                evidence_sha256=str(reference["sha256"]), gate_family="compile",
            )

    def test_promotion_rehashes_content_addressed_evidence(self) -> None:
        records = {}
        ordered = ["compile", *sorted(CANDIDATE_REQUIRED_GATES - {"compile"})]
        for family in ordered:
            record_id = f"{family}-rehash"
            self.record_candidate_host_gate(family, "passed", record_id)
            records[family] = record_id
        self.record_candidate_host_gate("final-verification", "passed", "final-rehash")
        with self.ledger.connect() as connection:
            path = connection.execute(
                """select evidence_path from verifier_records
                   where record_id=?""",
                (records["compile"],),
            ).fetchone()[0]
        evidence = self.harness.joinpath(*Path(path).parts)
        evidence.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(LedgerError, "content hash changed"):
            self.ledger.promote_last_good_from_verification(
                run_id="run",
                unit_id="unit",
                candidate_artifact_id=self.candidate_id,
                verifier_record_id=records["compile"],
                gate_record_id="final-rehash",
            )

    def test_schema_fingerprint_detects_missing_index_and_trigger(self) -> None:
        for kind, name in (
            ("index", "project_gates_latest"),
            ("trigger", "candidate_sets_no_update"),
        ):
            with self.subTest(kind=kind):
                path = self.out_root / f"tampered-{kind}.sqlite3"
                ProjectLedger(path)
                connection = sqlite3.connect(path)
                connection.execute(f"drop {kind} {name}")
                connection.commit()
                connection.close()
                with self.assertRaisesRegex(SchemaVersionError, "fingerprint"):
                    ProjectLedger(path)

if __name__ == "__main__":
    unittest.main()
