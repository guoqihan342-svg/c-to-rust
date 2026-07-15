from __future__ import annotations

import copy
import hashlib
import json
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from validation.tools._project_migration_harness.artifacts import (
    content_sha256,
    write_json_artifact,
)
from validation.tools._project_migration_harness.c_toolchain_test_support import (
    FakeToolchain,
)
from validation.tools._project_migration_harness.clang_toolchain_binding import (
    persist_clang_toolchain_binding,
)
from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)
from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.project_candidate_domain import (
    validate_candidate_project_domain,
)
from validation.tools._project_migration_harness.project_interface_domain_sources import (
    reopen_project_interface_source_domain,
)
from validation.tools._project_migration_harness.project_interface_validation_domain import (
    materialize_project_interface_validation_domain,
    reopen_project_interface_validation_domain,
)
from validation.tools.project_migration_rust_project_test_support import (
    bound_ir,
    descriptor,
)


MAIN = (
    "validation.tools._project_migration_harness."
    "project_interface_validation_domain"
)
SOURCES = (
    "validation.tools._project_migration_harness."
    "project_interface_domain_sources"
)
PROJECTION = (
    "validation.tools._project_migration_harness."
    "project_interface_validation_domain_projection"
)


class ProjectInterfaceValidationDomainTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="interface-domain-d0-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repo"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "src/input.c").write_bytes(b"source")
        descriptors = [
            descriptor(self.root, "unit-a", "pub fn a() -> i32 { 1 }\n"),
            descriptor(self.root, "unit-b", "pub fn b() -> i32 { 2 }\n"),
        ]
        self.ir, self.dag = bound_ir(
            self.root, descriptors, {"unit-a": [], "unit-b": ["unit-a"]},
        )
        self.ir_ref = write_json_artifact(
            self.root, "plan/rust-project-ir.json", self.ir,
        )
        self.out = self.root / "target/run"
        self.database = self.out / "state/project-migration.sqlite3"
        ProjectLedger(self.database)
        self.fake = FakeToolchain(self.root / "host")
        self.environment = {"PATH": str(self.root / "private-bin")}
        self.toolchain = persist_clang_toolchain_binding(
            self.out, profile="development", environment=self.environment,
            resolver=self.fake.resolver, runner=self.fake.runner,
        )
        self.contract = self._contract(self.ir["bindings"]["migration_dag"])
        self.manifest, self.candidate_sha = self._candidate_manifest()
        with self._verified_build_ir():
            self.sources, _ = reopen_project_interface_source_domain(
                self.ir, repo_root=self.repo, artifact_root=self.root,
            )
        self.candidate_domain = validate_candidate_project_domain(
            run_id="run", migration_contract=self.contract,
            rust_project_ir=self.ir,
            rust_project_binding_sha256=self.sources[
                "rust_project_binding_sha256"
            ], candidate_set_sha256=self.candidate_sha,
            candidate_set_manifest=self.manifest, artifact_root=self.root,
        )
        self.b2a = {
            "status": "candidate-verified", **self.candidate_domain,
            "verification_context_sha256": "7" * 64,
            "materialization": {"generation": {"sha256": "8" * 64}},
            "cargo_fact_evidence": {"binding_sha256": "9" * 64},
        }
        self.b2a_ref = write_content_addressed_json(
            self.out, "candidate-project-verification", {"fixture": True},
        )

    def test_materialize_and_reopen_compact_deep_domain(self) -> None:
        with self._dependencies() as plans:
            result = self._materialize()
            reopened = self._reopen(result["reference"])
        domain = result["domain"]
        self.assertEqual(domain, reopened)
        self.assertEqual(2, domain["candidate_set"]["member_count"])
        self.assertEqual(2, domain["clang_fact_plans"]["plan_count"])
        self.assertFalse(domain["claim_boundary"]["interface_closure"])
        self.assertEqual(2, plans.plans.call_count)
        serialized = json.dumps(domain, sort_keys=True)
        self.assertNotIn(str(self.fake.paths["clang"]), serialized)
        self.assertNotIn(str(self.repo), serialized)

    def test_contract_candidate_and_b2a_exchange_fail_closed(self) -> None:
        changed_contract = copy.deepcopy(self.contract)
        changed_contract["integration_manifest"]["sha256"] = "0" * 64
        cases = [
            ("contract", {"contract": changed_contract}),
            ("manifest", {"manifest": {
                **self.manifest,
                "members": [
                    {**self.manifest["members"][0], "content_sha256": "0" * 64},
                    self.manifest["members"][1],
                ],
            }}),
            ("b2a", {"b2a": {**self.b2a, "status": "failed"}}),
        ]
        for label, overrides in cases:
            with self.subTest(label=label), self._dependencies(**overrides):
                with self.assertRaises((ValueError, LedgerError)):
                    self._materialize()

    def test_source_and_live_toolchain_drift_block_reopen(self) -> None:
        with self._dependencies():
            result = self._materialize()
        candidate = self.root / self.ir["bindings"]["candidates"][0]["source"]["path"]
        candidate.write_text("pub fn changed() {}\n", encoding="utf-8")
        with self._dependencies(), self.assertRaises((ValueError, LedgerError)):
            self._reopen(result["reference"])
        candidate.write_bytes(b"pub fn a() -> i32 { 1 }\n")
        self.fake.paths["clang"].write_bytes(b"changed-clang")
        with self._dependencies(), self.assertRaisesRegex(LedgerError, "drifted"):
            self._reopen(result["reference"])

    def test_parent_child_dag_binds_the_run_contract_parent(self) -> None:
        child = copy.deepcopy(self.dag)
        child["parent_migration_dag"] = {
            "scope": "verification-dependency-closure",
            "artifact": self.ir["bindings"]["migration_dag"],
            "selected_unit_ids": ["unit-a", "unit-b"],
        }
        child_ref = write_json_artifact(self.root, "plan/child-dag.json", child)
        child_ir = copy.deepcopy(self.ir)
        child_ir["bindings"]["migration_dag"] = child_ref
        child_ir["ir_sha256"] = content_sha256({
            key: value for key, value in child_ir.items() if key != "ir_sha256"
        })
        self.ir = child_ir
        self.ir_ref = write_json_artifact(
            self.root, "plan/child-rust-project-ir.json", child_ir,
        )
        with self._verified_build_ir():
            self.sources, _ = reopen_project_interface_source_domain(
                child_ir, repo_root=self.repo, artifact_root=self.root,
            )
        projection = {
            **self.candidate_domain,
            "rust_project_ir_sha256": child_ir["ir_sha256"],
            "rust_project_binding_sha256": self.sources[
                "rust_project_binding_sha256"
            ],
        }
        projection["candidate_domain_context_sha256"] = content_sha256({
            key: projection[key] for key in (
                "run_id", "run_context_sha256", "dag_sha256",
                "integration_manifest", "candidate_set_sha256",
                "candidate_set_manifest_sha256", "rust_project_ir_sha256",
                "rust_project_interface_sha256", "rust_project_binding_sha256",
            )
        })
        self.b2a = {**self.b2a, **projection}
        with self._dependencies():
            domain = self._materialize()["domain"]
        self.assertEqual(
            content_sha256(self.sources["dag"]), domain["source_domain"]["dag_sha256"],
        )

    def _materialize(self) -> dict:
        return materialize_project_interface_validation_domain(
            ledger_path=self.database, run_id="run",
            candidate_set_sha256=self.candidate_sha,
            base_rust_project_ir=self.ir_ref,
            candidate_project_verification=self.b2a_ref,
            clang_toolchain_receipt=self.toolchain, repo_root=self.repo,
            artifact_root=self.root, harness_root=self.root,
            quarantine_root=self.root / "quarantine", out_root=self.out,
            environment=self.environment, resolver=self.fake.resolver,
            runner=self.fake.runner,
        )

    def _reopen(self, reference: dict) -> dict:
        return reopen_project_interface_validation_domain(
            self.database, reference, repo_root=self.repo,
            artifact_root=self.root, harness_root=self.root,
            quarantine_root=self.root / "quarantine",
            environment=self.environment, resolver=self.fake.resolver,
            runner=self.fake.runner,
        )

    def _dependencies(
        self, *, contract: dict | None = None, manifest: dict | None = None,
        b2a: dict | None = None,
    ) -> ExitStack:
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(self._verified_build_ir())
        stack.enter_context(patch(
            f"{MAIN}.load_migration_contract",
            return_value=(contract or self.contract, self.dag),
        ))
        stack.enter_context(patch(
            f"{MAIN}.candidate_set_manifest",
            return_value=manifest or self.manifest,
        ))
        stack.enter_context(patch(
            f"{MAIN}.reopen_candidate_project_verification",
            return_value=b2a or self.b2a,
        ))
        plans = stack.enter_context(patch(
            f"{PROJECTION}.build_clang_fact_plans",
            side_effect=self._plans,
        ))
        stack.enter_context(patch(
            f"{PROJECTION}.validate_clang_fact_plan",
            side_effect=lambda plan, *_: plan,
        ))
        stack.plans = plans
        return stack

    @staticmethod
    def _plans(build_ir: dict, _: dict) -> list[dict]:
        unit = build_ir["translation_units"][0]["unit_id"]
        return [{
            "build_ir_semantic_sha256": build_ir["semantic_sha256"],
            "unit_id": unit, "gate": gate,
            "plan_sha256": content_sha256({"unit": unit, "gate": gate}),
            "target_context_sha256": "6" * 64,
        } for gate in ("clang-ast", "clang-record-layout")]

    @staticmethod
    def _verified_build_ir():
        return patch(
            f"{SOURCES}.verify_build_ir_artifact",
            return_value={
                "status": "verified", "toolchain_profile": "development",
                "verified_binding_count": 2,
                "native_link_config_resolved": True,
                "unresolved_native_dependency_count": 0,
            },
        )

    def _contract(self, reference: dict) -> dict:
        core = {
            "schema_version": 1, "run_id": "run", "dag_sha256": "d" * 64,
            "integration_manifest": reference,
            "dependency_edges": [
                {"unit_id": key, "dependencies": self.dag["dag"][key]}
                for key in sorted(self.dag["dag"])
            ], "dag_order": self.dag["dag_order"],
        }
        return {**core, "context_sha256": content_sha256(core)}

    def _candidate_manifest(self) -> tuple[dict, str]:
        members = [{
            "unit_id": item["unit_id"], "artifact_id": item["artifact_id"],
            "content_sha256": item["source"]["sha256"],
        } for item in self.ir["bindings"]["candidates"]]
        manifest = {
            "schema_version": 2, "scope": "project-final",
            "run_context_sha256": self.contract["context_sha256"],
            "dag_sha256": self.contract["dag_sha256"],
            "integration_manifest_sha256": self.contract[
                "integration_manifest"
            ]["sha256"], "roots": [item["unit_id"] for item in members],
            "members": members,
        }
        compact = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        return manifest, hashlib.sha256(compact.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    unittest.main()
