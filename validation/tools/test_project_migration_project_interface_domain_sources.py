from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from validation.tools._project_migration_harness.artifacts import (
    content_sha256,
    write_json_artifact,
)
from validation.tools._project_migration_harness.project_interface_domain_sources import (
    reopen_project_interface_source_domain,
)
from validation.tools.project_migration_rust_project_test_support import (
    bound_ir,
    descriptor,
)


MODULE = (
    "validation.tools._project_migration_harness."
    "project_interface_domain_sources"
)


class ProjectInterfaceDomainSourcesTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="interface-domain-sources-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repo"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "src" / "input.c").write_bytes(b"source")
        descriptors = [
            descriptor(self.root, "unit-a", "pub fn a() -> i32 { 1 }\n"),
            descriptor(self.root, "unit-b", "pub fn b() -> i32 { 2 }\n"),
        ]
        self.ir, self.dag = bound_ir(
            self.root, descriptors, {"unit-a": [], "unit-b": ["unit-a"]},
        )

    def test_reopens_dag_all_build_irs_candidates_and_repository_binding(self) -> None:
        with self._verified_build_ir():
            domain, build_irs = reopen_project_interface_source_domain(
                self.ir, repo_root=self.repo, artifact_root=self.root,
            )
        self.assertEqual(1, len(build_irs))
        self.assertEqual(1, len(domain["build_ir_set"]))
        self.assertEqual(2, len(domain["candidate_sources"]))
        self.assertIsNone(domain["dag"]["parent"])
        self.assertEqual(
            self.ir["bindings"]["migration_dag"],
            domain["dag"]["child"]["artifact"],
        )
        self.assertFalse(domain["claim_boundary"]["interface_closure"])
        self.assertEqual(64, len(domain["source_repository_binding_sha256"]))

    def test_parent_child_cohort_is_bound_without_copying_parent_payload(self) -> None:
        child = copy.deepcopy(self.dag)
        child["parent_migration_dag"] = {
            "scope": "verification-dependency-closure",
            "artifact": self.ir["bindings"]["migration_dag"],
            "selected_unit_ids": ["unit-a", "unit-b"],
        }
        child_ref = write_json_artifact(self.root, "plan/child-dag.json", child)
        ir = copy.deepcopy(self.ir)
        ir["bindings"]["migration_dag"] = child_ref
        ir["ir_sha256"] = content_sha256({
            key: value for key, value in ir.items() if key != "ir_sha256"
        })
        with self._verified_build_ir():
            domain, _ = reopen_project_interface_source_domain(
                ir, repo_root=self.repo, artifact_root=self.root,
            )
        self.assertEqual(
            "verification-dependency-closure", domain["dag"]["parent"]["scope"],
        )
        self.assertEqual(
            self.ir["bindings"]["migration_dag"],
            domain["dag"]["parent"]["artifact"],
        )

    def test_any_build_ir_repository_reprojection_failure_blocks_domain(self) -> None:
        with patch(
            f"{MODULE}.verify_build_ir_artifact",
            return_value={"status": "blocked", "blockers": [{"kind": "source_drift"}]},
        ):
            with self.assertRaisesRegex(
                ValueError, "interface_validation_c_repository_drifted",
            ):
                reopen_project_interface_source_domain(
                    self.ir, repo_root=self.repo, artifact_root=self.root,
                )

    def test_candidate_or_build_ir_content_drift_is_rejected_before_projection(self) -> None:
        candidate = self.root / self.ir["bindings"]["candidates"][0]["source"]["path"]
        candidate.write_text("pub fn changed() {}\n", encoding="utf-8")
        with self._verified_build_ir(), self.assertRaises(ValueError):
            reopen_project_interface_source_domain(
                self.ir, repo_root=self.repo, artifact_root=self.root,
            )

    @staticmethod
    def _verified_build_ir():
        return patch(
            f"{MODULE}.verify_build_ir_artifact",
            return_value={
                "status": "verified",
                "toolchain_profile": "development",
                "verified_binding_count": 2,
                "native_link_config_resolved": True,
                "unresolved_native_dependency_count": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
