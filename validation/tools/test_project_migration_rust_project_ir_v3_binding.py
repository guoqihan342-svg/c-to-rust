from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from validation.tools.project_migration_build_ir_host_test_support import (
    BuildIRHostBindingTestCase,
)
from validation.tools._project_migration_harness.artifacts import (
    content_sha256, write_json_artifact,
)
from validation.tools._project_migration_harness.build_ir import finalize_build_ir
from validation.tools._project_migration_harness.build_ir_projection import target_closure
from validation.tools._project_migration_harness.migration_target_scope import (
    derive_build_ir_target_scopes,
)
from validation.tools._project_migration_harness.rust_candidate_facts import (
    derive_rust_metadata,
)
from validation.tools._project_migration_harness.rust_project_ir_v3_derivation import (
    derive_rust_project_ir_v3_from_candidates,
)
from validation.tools._project_migration_harness.rust_project_ir_validation import (
    interface_projection, reopen_rust_project_ir_bindings,
)


class RustProjectIRV3BindingTests(unittest.TestCase):
    def setUp(self) -> None:
        host = BuildIRHostBindingTestCase(methodName="runTest")
        host.setUp()
        self.addCleanup(host.doCleanups)
        self.build_ir = host.standard_build_ir()
        self.temporary = tempfile.TemporaryDirectory(prefix="rust-project-ir-v3-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.build_ref = write_json_artifact(
            self.root, "plan/build-ir.json", self.build_ir,
        )
        unit_id = str(self.build_ir["translation_units"][0]["unit_id"])
        self.group_id = "group-a"
        self.scope = derive_build_ir_target_scopes(
            [self.build_ir], {self.group_id: [unit_id]},
        )[self.group_id]
        graph = {
            "schema_version": 1, "status": "ready",
            "sccs": [{
                "scc_id": self.group_id, "dependency_scc_ids": [],
                "source_unit_ids": [unit_id], "target_scope": self.scope,
            }],
            "waves": [{"wave_index": 0, "scc_ids": [self.group_id]}],
        }
        self.graph_ref = write_json_artifact(
            self.root, "plan/migration-graph.json", graph,
        )
        placeholder = {"path": "plan/placeholder.json", "sha256": "f" * 64,
                       "size_bytes": 1}
        self.manifest = {
            "schema_version": 1,
            "dag": {self.group_id: []}, "dag_order": [self.group_id],
            "build_ir": {
                "status": "bound", "artifact": self.build_ref,
                "verification": placeholder, "worker_admission": placeholder,
            },
            "migration_graph": self.graph_ref,
            "target_scopes": {self.group_id: {
                "group_content_sha256": "e" * 64,
                "scope_sha256": self.scope["scope_sha256"],
            }},
            "claim_boundary": {
                "semantic_gate": False, "translation_coverage_numerator": 0,
            },
        }
        self.dag_ref = write_json_artifact(
            self.root, "plan/integration-manifest.json", self.manifest,
        )
        source = "pub fn migrated_unit() -> i32 { 7 }\n"
        source_path = self.root / "candidates/group-a.rs"
        source_path.parent.mkdir(parents=True)
        raw = source.encode("utf-8")
        source_path.write_bytes(raw)
        self.descriptor = {
            "unit_id": self.group_id, "group_id": self.group_id,
            "artifact_id": "candidate-group-a", "status": "accepted",
            "source_path": "candidates/group-a.rs",
            "sha256": hashlib.sha256(raw).hexdigest(),
            **derive_rust_metadata(source),
        }
        self.ir = derive_rust_project_ir_v3_from_candidates(
            migration_manifest=self.manifest, migration_dag_ref=self.dag_ref,
            build_ir_refs=[self.build_ref],
            candidate_descriptors=[self.descriptor], artifact_root=self.root,
        )

    def test_candidate_derives_multi_product_v3_and_reopens_from_disk(self) -> None:
        result = reopen_rust_project_ir_bindings(self.ir, self.root)

        self.assertEqual("v3-domain-bound", result["status"])
        self.assertEqual(2, result["package_count"])
        self.assertEqual(2, result["target_count"])
        self.assertEqual(2, result["module_count"])
        self.assertEqual("ready", self.ir["topology_status"])
        self.assertFalse(result["semantic_gate"])
        self.assertFalse(result["semantic_pass"])

    def test_binding_uses_artifact_sha_instead_of_build_semantic_sha(self) -> None:
        evidence = self.ir["workspace"]["evidence"]["build_ir_sha256s"]

        self.assertEqual([self.build_ref["sha256"]], evidence)
        self.assertNotEqual(self.build_ir["semantic_sha256"], evidence[0])

    def test_ordered_input_drift_rehashes_but_fails_recomputation(self) -> None:
        forged = copy.deepcopy(self.ir)
        forged["targets"][0]["ordered_link_arguments"].append("-lforged")
        self._rehash(forged)

        with self.assertRaisesRegex(ValueError, "topology drifted"):
            reopen_rust_project_ir_bindings(forged, self.root)

    def test_explicit_graph_binding_must_match_manifest(self) -> None:
        forged = copy.deepcopy(self.ir)
        forged["bindings"]["migration_graph"] = {
            "path": "plan/other-graph.json", "sha256": "a" * 64,
            "size_bytes": 1,
        }
        forged["ir_sha256"] = content_sha256({
            key: item for key, item in forged.items() if key != "ir_sha256"
        })

        with self.assertRaisesRegex(ValueError, "different migration graphs"):
            reopen_rust_project_ir_bindings(forged, self.root)

    def test_object_only_blocked_topology_can_be_reopened_without_credit(self) -> None:
        build_ir = copy.deepcopy(self.build_ir)
        build_ir["targets"] = [
            item for item in build_ir["targets"] if item["kind"] == "object"
        ]
        build_ir["target_closure"] = target_closure(build_ir["targets"])
        build_ir["external_dependencies"] = []
        build_ir = finalize_build_ir(build_ir)
        build_ref = write_json_artifact(
            self.root, "plan/object-only-build-ir.json", build_ir,
        )
        unit_id = str(build_ir["translation_units"][0]["unit_id"])
        scope = derive_build_ir_target_scopes(
            [build_ir], {self.group_id: [unit_id]},
        )[self.group_id]
        graph = {
            "schema_version": 1, "status": "ready",
            "sccs": [{
                "scc_id": self.group_id, "dependency_scc_ids": [],
                "source_unit_ids": [unit_id], "target_scope": scope,
            }],
            "waves": [{"wave_index": 0, "scc_ids": [self.group_id]}],
        }
        graph_ref = write_json_artifact(
            self.root, "plan/object-only-graph.json", graph,
        )
        manifest = copy.deepcopy(self.manifest)
        manifest["build_ir"]["artifact"] = build_ref
        manifest["migration_graph"] = graph_ref
        manifest["target_scopes"][self.group_id]["scope_sha256"] = scope["scope_sha256"]
        dag_ref = write_json_artifact(
            self.root, "plan/object-only-manifest.json", manifest,
        )
        ir = derive_rust_project_ir_v3_from_candidates(
            migration_manifest=manifest, migration_dag_ref=dag_ref,
            build_ir_refs=[build_ref], candidate_descriptors=[self.descriptor],
            artifact_root=self.root,
        )

        result = reopen_rust_project_ir_bindings(ir, self.root)
        self.assertEqual("blocked", ir["topology_status"])
        self.assertEqual([], ir["packages"])
        self.assertEqual("v3-domain-bound", result["status"])
        self.assertFalse(result["semantic_gate"])

    def test_candidate_descriptor_hash_drift_fails_before_ir_creation(self) -> None:
        descriptor = copy.deepcopy(self.descriptor)
        descriptor["sha256"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "candidate_source_hash_drift"):
            derive_rust_project_ir_v3_from_candidates(
                migration_manifest=self.manifest, migration_dag_ref=self.dag_ref,
                build_ir_refs=[self.build_ref], candidate_descriptors=[descriptor],
                artifact_root=self.root,
            )

    @staticmethod
    def _rehash(value: dict) -> None:
        value["interface_sha256"] = content_sha256(interface_projection(value))
        value["ir_sha256"] = content_sha256({
            key: item for key, item in value.items() if key != "ir_sha256"
        })


if __name__ == "__main__":
    unittest.main()
