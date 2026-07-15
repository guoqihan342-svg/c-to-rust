from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.rust_cargo_topology_evidence import (
    materialize_rust_cargo_topology_evidence,
    reopen_rust_cargo_topology_evidence,
)


MODULE = (
    "validation.tools._project_migration_harness."
    "rust_cargo_topology_evidence"
)


class RustCargoTopologyEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="rust-cargo-topology-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out = self.root / "target/run"
        self.database = self.out / "state/project-migration.sqlite3"
        self.database.parent.mkdir(parents=True)
        self.database.touch()
        self.b2a_ref = write_content_addressed_json(
            self.out, "candidate-project-verification", {"fixture": True},
        )
        self.domain_ref = write_content_addressed_json(
            self.out, "project-interface-validation-domain", {"fixture": True},
        )
        self.domain = {
            "domain_sha256": "0" * 64,
            "run": {"run_id": "run"},
            "candidate_set": {"sha256": "5" * 64},
            "rust_project_ir": {
                "ir_sha256": "6" * 64, "interface_sha256": "7" * 64,
            },
            "candidate_project_verification": {"reference": self.b2a_ref},
        }
        self.b2a = {
            "status": "candidate-verified",
            "verification_context_sha256": "1" * 64,
            "materialization": {"generation": {"sha256": "2" * 64}},
            "cargo_fact_evidence": {"binding_sha256": "3" * 64},
            "execution": {"fixture": "execution"},
            "cargo_observations": {"fixture": "observations"},
        }
        self.payloads = {
            "binding": {"binding_sha256": "3" * 64},
            "cargo_metadata": {"fixture": "metadata"},
            "compiler_artifacts": {"fixture": "compiler"},
        }
        self.witness = {
            "status": "ready", "witness_sha256": "4" * 64,
            "claim_boundary": {"section_closure": False},
        }

    def test_materialize_and_reopen_bind_b2a_and_rederived_payloads(self) -> None:
        with self._dependencies() as calls:
            result = self._materialize()
            reopened = self._reopen(result["reference"])
        self.assertEqual(result["receipt"], reopened)
        self.assertEqual(
            self.b2a_ref,
            reopened["candidate_project_verification"]["reference"],
        )
        self.assertEqual(
            self.domain_ref, reopened["validation_domain"]["reference"],
        )
        self.assertEqual("3" * 64, reopened[
            "candidate_project_verification"
        ]["cargo_fact_binding_sha256"])
        self.assertEqual(2, calls["b2a"].call_count)
        self.assertEqual(2, calls["domain"].call_count)
        self.assertEqual(2, calls["payloads"].call_count)
        self.assertFalse(reopened["claim_boundary"]["section_closure"])

    def test_reopen_rejects_current_domain_or_b2a_context_drift(self) -> None:
        with self._dependencies():
            result = self._materialize()
        changed = copy.deepcopy(self.b2a)
        changed["verification_context_sha256"] = "9" * 64
        with self._dependencies(b2a=changed), self.assertRaisesRegex(
            LedgerError, "drifted",
        ):
            self._reopen(result["reference"])
        changed_domain = {**self.domain, "domain_sha256": "8" * 64}
        with self._dependencies(domain=changed_domain), self.assertRaisesRegex(
            LedgerError, "drifted",
        ):
            self._reopen(result["reference"])

    def test_fixed_output_root_and_candidate_verified_status_are_required(self) -> None:
        with self._dependencies(), self.assertRaisesRegex(
            LedgerError, "output root",
        ):
            self._materialize(out_root=self.root)
        blocked = {**self.b2a, "status": "blocked"}
        with self._dependencies(b2a=blocked), self.assertRaisesRegex(
            LedgerError, "candidate-verified",
        ):
            self._materialize()

    def _materialize(self, *, out_root: Path | None = None) -> dict:
        return materialize_rust_cargo_topology_evidence(
            ledger_path=self.database, out_root=out_root or self.out,
            validation_domain=self.domain_ref, repo_root=self.root / "repo",
            artifact_root=self.root, harness_root=self.root,
            quarantine_root=self.root / "quarantine",
        )

    def _reopen(self, reference: dict) -> dict:
        return reopen_rust_cargo_topology_evidence(
            self.database, reference,
            repo_root=self.root / "repo", artifact_root=self.root,
            harness_root=self.root, quarantine_root=self.root / "quarantine",
        )

    def _dependencies(
        self, *, domain: dict | None = None, b2a: dict | None = None,
    ):
        stack = _PatchStack()
        self.addCleanup(stack.close)
        calls = {}
        calls["domain"] = stack.enter(patch(
            f"{MODULE}.reopen_project_interface_validation_domain",
            return_value=domain or self.domain,
        ))
        calls["b2a"] = stack.enter(patch(
            f"{MODULE}.reopen_candidate_project_verification",
            return_value=b2a or self.b2a,
        ))
        calls["payloads"] = stack.enter(patch(
            f"{MODULE}.reopen_candidate_cargo_fact_payloads",
            return_value=self.payloads,
        ))
        stack.enter(patch(
            f"{MODULE}.build_rust_cargo_topology_witness",
            return_value=self.witness,
        ))
        stack.calls = calls
        return stack


class _PatchStack:
    def __init__(self) -> None:
        self._patches = []
        self.calls = {}

    def enter(self, context):
        value = context.__enter__()
        self._patches.append(context)
        return value

    def close(self) -> None:
        while self._patches:
            self._patches.pop().__exit__(None, None, None)

    def __enter__(self):
        return self.calls

    def __exit__(self, *_):
        self.close()


if __name__ == "__main__":
    unittest.main()
