from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.project_candidate_domain import (
    candidate_verification_context,
    validate_candidate_project_domain,
)
from validation.tools._project_migration_harness.rust_project_ir_validation import (
    reopen_rust_project_ir_bindings,
)
from validation.tools.project_migration_rust_project_test_support import (
    bound_ir,
    descriptor,
)


class ProjectCandidateDomainTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="candidate-project-domain-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        descriptors = [
            descriptor(self.root, "unit-a", "pub fn a() -> i32 { 1 }\n"),
            descriptor(self.root, "unit-b", "pub fn b() -> i32 { 2 }\n"),
        ]
        self.ir, self.dag = bound_ir(
            self.root, descriptors, {"unit-a": [], "unit-b": ["unit-a"]},
        )
        self.binding = reopen_rust_project_ir_bindings(self.ir, self.root)
        payload = {
            "schema_version": 1,
            "run_id": "domain-run",
            "dag_sha256": "d" * 64,
            "integration_manifest": self.ir["bindings"]["migration_dag"],
            "dependency_edges": [
                {"unit_id": unit_id, "dependencies": dependencies}
                for unit_id, dependencies in sorted(self.dag["dag"].items())
            ],
            "dag_order": self.dag["dag_order"],
        }
        self.contract = {**payload, "context_sha256": content_sha256(payload)}
        members = [{
            "unit_id": item["unit_id"],
            "artifact_id": item["artifact_id"],
            "content_sha256": item["source"]["sha256"],
        } for item in self.ir["bindings"]["candidates"]]
        self.manifest = {
            "schema_version": 2,
            "scope": "project-final",
            "run_context_sha256": self.contract["context_sha256"],
            "dag_sha256": self.contract["dag_sha256"],
            "integration_manifest_sha256": self.contract[
                "integration_manifest"
            ]["sha256"],
            "roots": [item["unit_id"] for item in members],
            "members": members,
        }
        self.candidate_set_sha256 = _compact_sha(self.manifest)

    def validate(self, *, contract=None, manifest=None, digest=None, ir=None):
        value = ir or self.ir
        return validate_candidate_project_domain(
            run_id="domain-run",
            migration_contract=contract or self.contract,
            rust_project_ir=value,
            rust_project_binding_sha256=self.binding["bindings_sha256"],
            candidate_set_sha256=digest or self.candidate_set_sha256,
            candidate_set_manifest=manifest or self.manifest,
            artifact_root=self.root,
        )

    def test_valid_domain_binds_run_dag_candidate_set_and_ir(self) -> None:
        result = self.validate()
        self.assertEqual("domain-run", result["run_id"])
        self.assertEqual(
            self.candidate_set_sha256, result["candidate_set_sha256"],
        )
        self.assertEqual(
            self.binding["bindings_sha256"],
            result["rust_project_binding_sha256"],
        )
        self.assertEqual(64, len(result["candidate_domain_context_sha256"]))

    def test_candidate_set_must_be_project_final_full_cohort(self) -> None:
        variants = []
        for field, value in (
            ("scope", "wave-provisional"),
            ("roots", ["unit-a"]),
            ("members", self.manifest["members"][:1]),
            ("run_context_sha256", "0" * 64),
        ):
            changed = copy.deepcopy(self.manifest)
            changed[field] = value
            variants.append((field, changed))
        for field, manifest in variants:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate(manifest=manifest, digest=_compact_sha(manifest))

    def test_candidate_set_digest_and_contract_context_are_recomputed(self) -> None:
        with self.assertRaisesRegex(ValueError, "set_manifest_drifted"):
            self.validate(digest="0" * 64)
        contract = copy.deepcopy(self.contract)
        contract["dag_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "run_context_drifted"):
            self.validate(contract=contract)

    def test_contract_and_ir_must_bind_the_same_live_dag(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["integration_manifest"] = {
            **contract["integration_manifest"], "path": "plan/other.json",
        }
        projection = {
            key: item for key, item in contract.items() if key != "context_sha256"
        }
        contract["context_sha256"] = content_sha256(projection)
        with self.assertRaisesRegex(ValueError, "contract_ir_dag_mismatch"):
            self.validate(contract=contract)

    def test_verification_context_changes_with_cargo_or_native_evidence(self) -> None:
        domain = self.validate()
        args = (
            domain,
            {"status": "verified"},
            {"generation": {"sha256": "1" * 64}},
            {"project_input_sha256": "1" * 64},
            {"cargo-check": {"outcome": "executed"}},
        )
        first = candidate_verification_context(
            *args, {"binding_sha256": "2" * 64},
        )
        second = candidate_verification_context(
            *args, {"binding_sha256": "3" * 64},
        )
        self.assertNotEqual(first, second)


def _compact_sha(value: dict) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


if __name__ == "__main__":
    unittest.main()
