from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness import cargo_project
from validation.tools._project_migration_harness.artifacts import (
    content_sha256, write_json_artifact,
)
from validation.tools._project_migration_harness.native_link_context import (
    build_native_link_context,
)
from validation.tools._project_migration_harness.native_link_model import (
    build_native_link_candidate,
)
from validation.tools._project_migration_harness.rust_project_cargo import (
    reconstruct_cargo_project_from_ir,
)
from validation.tools._project_migration_harness.rust_project_ir import (
    bind_native_link_candidate,
)
from validation.tools._project_migration_harness.rust_project_ir_derivation import (
    derive_rust_project_ir_from_candidates,
)
from validation.tools._project_migration_harness.rust_project_ir_validation import (
    reopen_rust_project_ir_bindings, validate_rust_project_ir,
)
from validation.tools.project_migration_native_link_test_support import (
    materialize_native_build_ir,
)
from validation.tools.project_migration_rust_project_test_support import descriptor


class RustProjectNativeLinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="rust-native-link-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_build_ir_requirements_enter_rust_project_ir_and_reopen(self) -> None:
        ir, _build_ir, _build_ref = self._derive("/private/libaurora.so.2")

        self.assertEqual(1, len(ir["native_link_requirements"]))
        self.assertEqual([], ir["native_link_plans"])
        self.assertIn(
            "native-link-config",
            ir["interface_completeness"]["unresolved_sections"],
        )
        binding = reopen_rust_project_ir_bindings(ir, self.root)
        self.assertEqual("domain-bound", binding["status"])

    def test_ai_candidate_materializes_only_portable_build_rs_directives(self) -> None:
        ir, build_ir, build_ref = self._derive("/private/libnebula.so")
        context = build_native_link_context(
            build_ir, build_ref, profile="competition",
        )
        requirement = context["requirements"][0]
        candidate = build_native_link_candidate(context, {
            "schema_version": 1,
            "artifact_kind": "native-link-model-response",
            "context_sha256": context["context_sha256"],
            "proposals": [{
                "requirement_id": requirement["requirement_id"],
                "strategy": "rustc-link-lib",
                "rustc_link_name": "nebula",
                "rustc_link_kind": "dylib",
            }],
        })

        bound = bind_native_link_candidate(ir, context, candidate)
        project = reconstruct_cargo_project_from_ir(bound, self.root)

        build_script = project.files["build.rs"].decode("ascii")
        self.assertIn("cargo:rustc-link-lib=dylib=nebula", build_script)
        self.assertNotIn("/private", build_script)
        self.assertIn('build = "build.rs"', project.files["Cargo.toml"].decode())
        native = project.last_good_manifest["native_link"]
        self.assertEqual("candidate-materialized", native["status"])
        self.assertEqual(candidate["candidate_sha256"], native["candidate_sha256"])
        self.assertFalse(native["resolution_gate"])
        self.assertFalse(bound["claim_boundary"]["semantic_gate"])

    def test_missing_or_unmaterialized_plan_cannot_generate_cargo(self) -> None:
        ir, build_ir, build_ref = self._derive("/private/libquasar.a")
        with self.assertRaisesRegex(
            cargo_project.ProjectInputError,
            "rust_project_ir_native_link_plan_missing",
        ):
            reconstruct_cargo_project_from_ir(ir, self.root)
        context = build_native_link_context(
            build_ir, build_ref, profile="development",
        )
        requirement = context["requirements"][0]
        candidate = build_native_link_candidate(context, {
            "schema_version": 1,
            "artifact_kind": "native-link-model-response",
            "context_sha256": context["context_sha256"],
            "proposals": [{
                "requirement_id": requirement["requirement_id"],
                "strategy": "ffi-boundary",
                "rustc_link_name": None,
                "rustc_link_kind": None,
            }],
        })
        bound = bind_native_link_candidate(ir, context, candidate)
        with self.assertRaisesRegex(
            cargo_project.ProjectInputError,
            "rust_project_ir_native_link_strategy_unmaterialized",
        ):
            reconstruct_cargo_project_from_ir(bound, self.root)

    def test_valid_requirement_forgery_is_rejected_against_bound_build_ir(self) -> None:
        ir, _build_ir, _build_ref = self._derive("/private/libzenith.so")
        forged = copy.deepcopy(ir)
        forged["native_link_requirements"][0]["dependency_count"] += 1
        forged["interface_sha256"] = content_sha256(
            self._interface_projection(forged)
        )
        forged["ir_sha256"] = content_sha256({
            key: item for key, item in forged.items() if key != "ir_sha256"
        })
        validate_rust_project_ir(forged)

        with self.assertRaisesRegex(ValueError, "requirements drifted"):
            reopen_rust_project_ir_bindings(forged, self.root)

    def _derive(self, external: str) -> tuple[dict, dict, dict]:
        _repo, _database, build_ir, build_ref = materialize_native_build_ir(
            self.root, "source", external,
        )
        item = descriptor(self.root, "unit", "pub fn value() -> i32 { 1 }\n")
        manifest = {
            "schema_version": 1,
            "profile": "competition",
            "dag": {"unit": []},
            "dag_order": ["unit"],
            "unsafe_policy": {
                "allow_unsafe": True, "max_total": None, "max_per_group": None,
            },
            "claim_boundary": {
                "semantic_gate": False, "translation_coverage_numerator": 0,
            },
        }
        dag_ref = write_json_artifact(
            self.root, "plan/integration-manifest.json", manifest,
        )
        ir = derive_rust_project_ir_from_candidates(
            migration_manifest=manifest,
            migration_dag_ref=dag_ref,
            build_ir_refs=[build_ref],
            candidate_descriptors=[item],
            artifact_root=self.root,
        )
        return ir, build_ir, build_ref

    @staticmethod
    def _interface_projection(value: dict) -> dict:
        from validation.tools._project_migration_harness.rust_project_ir_validation import (
            interface_projection,
        )
        return interface_projection(value)


if __name__ == "__main__":
    unittest.main()
