from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import (
    write_json_artifact,
)
from validation.tools._project_migration_harness.native_link_context import (
    build_native_link_context,
)
from validation.tools._project_migration_harness.native_link_model import (
    build_native_link_candidate,
)
from validation.tools._project_migration_harness.project_native_link_state import (
    recover_project_native_link_state,
)
from validation.tools._project_migration_harness.rust_project_ir import (
    bind_native_link_candidate,
)
from validation.tools._project_migration_harness.rust_project_ir_derivation import (
    derive_rust_project_ir_from_candidates,
)
from validation.tools.project_migration_native_link_test_support import (
    materialize_native_build_ir,
)
from validation.tools.project_migration_rust_project_test_support import descriptor


class ProjectNativeLinkStateTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-native-state-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        _repo, _database, self.build_ir, self.build_ref = (
            materialize_native_build_ir(
                self.root, "source", "/private/libgeneric.so.2",
            )
        )
        item = descriptor(
            self.root, "unit", "pub fn value() -> i32 { 1 }\n",
        )
        self.manifest = {
            "schema_version": 1,
            "profile": "competition",
            "dag": {"unit": []},
            "dag_order": ["unit"],
            "build_ir": {"status": "bound", "artifact": self.build_ref},
            "unsafe_policy": {
                "allow_unsafe": True, "max_total": None, "max_per_group": None,
            },
            "claim_boundary": {
                "semantic_gate": False, "translation_coverage_numerator": 0,
            },
        }
        dag_ref = write_json_artifact(
            self.root, "plan/integration-manifest.json", self.manifest,
        )
        self.ir = derive_rust_project_ir_from_candidates(
            migration_manifest=self.manifest,
            migration_dag_ref=dag_ref,
            build_ir_refs=[self.build_ref],
            candidate_descriptors=[item],
            artifact_root=self.root,
        )
        self.context = build_native_link_context(
            self.build_ir, self.build_ref, profile="competition",
        )
        requirement = self.context["requirements"][0]
        self.candidate = build_native_link_candidate(self.context, {
            "schema_version": 1,
            "artifact_kind": "native-link-model-response",
            "context_sha256": self.context["context_sha256"],
            "proposals": [{
                "requirement_id": requirement["requirement_id"],
                "strategy": "rustc-link-lib",
                "rustc_link_name": "generic",
                "rustc_link_kind": "dylib",
            }],
        })

    def test_rebuilds_exact_candidate_from_bound_ir_plans(self) -> None:
        bound = bind_native_link_candidate(
            self.ir, self.context, self.candidate,
        )
        state = recover_project_native_link_state(
            bound, self.manifest, self.root,
        )
        self.assertEqual("candidate-ready", state["status"])
        self.assertEqual(self.context, state["context"])
        self.assertEqual(self.candidate, state["candidate"])
        self.assertFalse(state["resolution_gate"])

    def test_missing_candidate_remains_explicitly_unresolved(self) -> None:
        state = recover_project_native_link_state(
            self.ir, self.manifest, self.root,
        )
        self.assertEqual("candidate-missing", state["status"])
        self.assertIsNone(state["candidate"])
        self.assertEqual(1, state["requirement_count"])

    def test_profile_or_candidate_binding_drift_fails_closed(self) -> None:
        bound = bind_native_link_candidate(
            self.ir, self.context, self.candidate,
        )
        drifted = {**self.manifest, "profile": "development"}
        with self.assertRaisesRegex(ValueError, "candidate_binding_drifted"):
            recover_project_native_link_state(bound, drifted, self.root)


if __name__ == "__main__":
    unittest.main()
