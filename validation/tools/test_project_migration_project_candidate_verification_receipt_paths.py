from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.project_candidate_verification_receipt import (
    reopen_candidate_project_verification,
    validate_candidate_project_verification,
)
from validation.tools._project_migration_harness.candidate_generation_reopen import (
    reopen_candidate_generation,
)
from validation.tools._project_migration_harness.integration_validation import digest
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.project_candidate_domain import (
    candidate_domain_context_sha256,
    candidate_verification_context,
)
from validation.tools._project_migration_harness import cargo_project


class ProjectCandidateVerificationReceiptPathTests(unittest.TestCase):
    def _fixture(self) -> tuple[object, dict]:
        from validation.tools.test_project_migration_project_candidate_verification_receipt import (
            ProjectCandidateVerificationReceiptTests,
        )
        case = ProjectCandidateVerificationReceiptTests(methodName="runTest")
        temporary = tempfile.TemporaryDirectory(prefix="candidate-path-")
        self.addCleanup(temporary.cleanup)
        case.repo = Path(temporary.name)
        case.out_root = case.repo / "target/run"
        case.out_root.mkdir(parents=True)
        case.ledger_path = case.out_root / "state/project-migration.sqlite3"
        case.quarantine_root = case.repo / "quarantine"
        from validation.tools.project_migration_candidate_receipt_test_support import (
            materialize_test_quarantine,
        )
        case.materialization = materialize_test_quarantine(case.quarantine_root)
        case.candidate_set_sha256 = case.materialization["candidate_set_sha256"]
        return case, case._payload()

    def _payload(self) -> dict:
        return self._fixture()[1]

    def test_generation_path_escape_forms_are_rejected(self) -> None:
        for value in ("../outside", "/absolute", r"generations\current", "."):
            payload = self._payload()
            payload["materialization"]["generation"]["path"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_candidate_project_verification(payload)

    def test_materialization_shape_is_exact(self) -> None:
        payload = copy.deepcopy(self._payload())
        payload["materialization"]["model_verified"] = True
        with self.assertRaises(ValueError):
            validate_candidate_project_verification(payload)

    def test_self_consistent_manifest_rewrite_cannot_change_candidate_set(self) -> None:
        case, payload = self._fixture()
        generation = case.quarantine_root / "generations/current"
        quarantine_path = generation / "migration-quarantine.json"
        quarantine = json.loads(quarantine_path.read_text(encoding="utf-8"))
        original_candidate_set = case.candidate_set_sha256
        changed_content = "9" * 64
        quarantine["candidate_set"]["manifest"]["members"][0][
            "content_sha256"
        ] = changed_content
        quarantine["candidate_bindings"][0]["content_sha256"] = changed_content
        forged_candidate_set = digest(json.dumps(
            quarantine["candidate_set"]["manifest"],
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8"))
        quarantine["candidate_set"]["sha256"] = forged_candidate_set
        quarantine_raw = cargo_project.canonical_json_bytes(quarantine)
        quarantine_path.write_bytes(quarantine_raw)

        manifest_path = generation / cargo_project.LAST_GOOD_MANIFEST
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        reference = next(
            item for item in manifest["files"]
            if item["path"] == "migration-quarantine.json"
        )
        reference.update({
            "sha256": digest(quarantine_raw), "size_bytes": len(quarantine_raw),
        })
        manifest["quarantine_manifest"]["sha256"] = digest(quarantine_raw)
        manifest_raw = cargo_project.canonical_json_bytes(manifest)
        manifest_path.write_bytes(manifest_raw)

        materialization = payload["materialization"]
        materialization["candidate_set"]["sha256"] = forged_candidate_set
        materialization["generation"]["sha256"] = digest(manifest_raw)
        materialization["manifest_ref"].update({
            "sha256": reference["sha256"],
            "size_bytes": reference["size_bytes"],
        })
        materialization["generation_manifest_ref"].update({
            "sha256": digest(manifest_raw), "size_bytes": len(manifest_raw),
        })
        payload["candidate_set_sha256"] = forged_candidate_set
        payload["candidate_domain_context_sha256"] = (
            candidate_domain_context_sha256(payload)
        )
        payload["verification_context_sha256"] = candidate_verification_context(
            payload, payload["build_ir_verification"], materialization,
            payload["execution"], payload["cargo_observations"],
            payload["native_link_settlement"],
        )
        validate_candidate_project_verification(payload)
        reference = case._write(payload)
        with self.assertRaisesRegex(LedgerError, "binding drifted"):
            reopen_candidate_project_verification(
                case.ledger_path, reference,
                quarantine_root=case.quarantine_root,
                run_id="receipt-run",
                candidate_set_sha256=original_candidate_set,
                rust_project_ir_sha256="a" * 64,
                rust_project_interface_sha256="b" * 64,
            )

    def test_linked_quarantine_root_is_rejected(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="candidate-link-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        actual = root / "actual"
        from validation.tools.project_migration_candidate_receipt_test_support import (
            materialize_test_quarantine,
        )
        materialization = materialize_test_quarantine(actual)
        linked = root / "linked"
        try:
            linked.symlink_to(actual, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlink unavailable: {error}")
        receipt_materialization = {
            **materialization,
            "candidate_set": {
                "sha256": materialization["candidate_set_sha256"],
                "member_count": 2,
            },
            "rust_project_ir_sha256": "a" * 64,
            "rust_project_interface_sha256": "b" * 64,
        }
        with self.assertRaisesRegex(LedgerError, "cannot be reopened"):
            reopen_candidate_generation(linked, receipt_materialization)


if __name__ == "__main__":
    unittest.main()
