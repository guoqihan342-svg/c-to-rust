from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness import (
    cargo_project, integration, quarantine_generation,
)
from validation.tools._project_migration_harness.project_rust_ir import derive_bound_project_ir
from validation.tools._project_migration_harness.rust_project_cargo import (
    GENERATOR, RUST_PROJECT_IR_FILE, reconstruct_cargo_project_from_ir,
)
from validation.tools._project_migration_harness.rust_project_ir import (
    build_rust_project_ir,
)
from validation.tools.project_migration_rust_project_test_support import (
    bound_ir, descriptor,
)


def rebuild(ir: dict, **changes: object) -> dict:
    values = {
        "migration_dag_ref": ir["bindings"]["migration_dag"],
        "build_ir_refs": ir["bindings"]["build_ir"],
        "candidate_refs": ir["bindings"]["candidates"],
        "crate": ir["crate"], "modules": ir["modules"],
        "public_api": ir["public_api"], "shared_types": ir["shared_types"],
        "global_ownership": ir["global_ownership"],
        "initialization": ir["initialization"],
        "ffi_boundaries": ir["ffi_boundaries"], "cfgs": ir["cfgs"],
        "features": ir["features"], "unsafe_obligations": ir["unsafe_obligations"],
    }
    values.update(changes)
    return build_rust_project_ir(**values)


class RustProjectCargoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="rust-project-cargo-")
        self.workspace = Path(self.temporary.name)
        self.root = self.workspace / "artifacts"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_production_modules_expose_no_descriptor_only_generation_writer(self) -> None:
        self.assertFalse(hasattr(integration, "integrate_candidates"))
        self.assertFalse(hasattr(integration, "reconstruct_cargo_project"))
        self.assertFalse(hasattr(quarantine_generation, "materialize_quarantine_generation"))
        self.assertFalse(hasattr(cargo_project, "reconstruct_cargo_project"))

    def test_reopened_ir_is_the_only_generation_input(self) -> None:
        first = descriptor(
            self.root, "alpha", "pub fn base_value() -> i32 { 4 }\n",
        )
        second = descriptor(
            self.root, "beta",
            "pub fn final_value() -> i32 { crate::base_value() }\n",
        )
        ir, _manifest = bound_ir(
            self.root, [second, first], {"alpha": [], "beta": ["alpha"]},
        )

        one = reconstruct_cargo_project_from_ir(ir, self.root)
        two = reconstruct_cargo_project_from_ir(deepcopy(ir), self.root)

        self.assertEqual(one.files, two.files)
        self.assertEqual(GENERATOR, one.last_good_manifest["generator"])
        self.assertEqual(ir["ir_sha256"], one.last_good_manifest["rust_project_ir_sha256"])
        self.assertEqual(ir["interface_sha256"], one.last_good_manifest["rust_project_interface_sha256"])
        self.assertEqual(
            "partial",
            one.last_good_manifest["rust_project_ir_completeness"]["status"],
        )
        self.assertIn(
            "public-signature",
            one.last_good_manifest["rust_project_ir_completeness"]["unresolved_sections"],
        )
        self.assertEqual(json.loads(one.files[RUST_PROJECT_IR_FILE]), ir)
        self.assertIn("src/lib.rs", one.files)
        self.assertEqual(["alpha", "beta"], list(one.accepted_group_ids))

    def test_source_metadata_or_ir_interface_drift_fails_closed(self) -> None:
        item = descriptor(self.root, "unit", "pub fn visible() {}\n")
        drifted_descriptor = dict(item, public_symbols=[])
        with self.assertRaisesRegex(cargo_project.ProjectInputError, "candidate_interface_metadata_drift"):
            bound_ir(self.root, [drifted_descriptor], {"unit": []})
        ir, _manifest = bound_ir(self.root, [item], {"unit": []})
        altered = rebuild(ir, public_api=[])
        with self.assertRaisesRegex(cargo_project.ProjectInputError, "rust_project_ir_public_api_drift"):
            reconstruct_cargo_project_from_ir(altered, self.root)

    def test_cross_unit_conflict_enters_repair_and_cannot_generate(self) -> None:
        left = descriptor(self.root, "left", "pub fn collision() -> i32 { 1 }\n")
        right = descriptor(self.root, "right", "pub fn collision() -> i32 { 2 }\n")
        ir, _manifest = bound_ir(self.root, [left, right], {"left": [], "right": []})
        with self.assertRaisesRegex(cargo_project.ProjectInputError, "duplicate_public_symbol"):
            reconstruct_cargo_project_from_ir(ir, self.root)

    def test_distinct_rust_exports_with_same_native_name_conflict(self) -> None:
        left = descriptor(
            self.root, "left",
            '#[export_name = r#"native_collision"#]\n'
            'pub extern "C" fn left_value() -> i32 { 1 }\n',
        )
        right = descriptor(
            self.root, "right",
            '#[export_name = "native_collision"]\n'
            'pub extern "C" fn right_value() -> i32 { 2 }\n',
        )
        ir, _manifest = bound_ir(
            self.root, [left, right], {"left": [], "right": []},
        )

        with self.assertRaisesRegex(
            cargo_project.ProjectInputError, "conflicting_ffi_boundary",
        ):
            reconstruct_cargo_project_from_ir(ir, self.root)

    def test_wave_ir_binds_a_dependency_closed_subdag_to_the_full_dag(self) -> None:
        base = descriptor(self.root, "base", "pub fn base_value() -> i32 { 3 }\n")
        leaf = descriptor(
            self.root, "leaf", "pub fn leaf_value() -> i32 { crate::base_value() }\n",
        )
        _ir, manifest = bound_ir(
            self.root, [base, leaf], {"base": [], "leaf": ["base"]},
        )
        parent_path = self.root / "plan/integration-manifest.json"
        parent_raw = parent_path.read_bytes()
        contract = {"integration_manifest": {
            "path": "plan/integration-manifest.json",
            "sha256": hashlib.sha256(parent_raw).hexdigest(),
            "size_bytes": len(parent_raw),
        }}

        cohort_ir = derive_bound_project_ir(
            migration_contract=contract, migration_manifest=manifest,
            candidate_descriptors=[base], artifact_root=self.root,
        )
        plan = reconstruct_cargo_project_from_ir(cohort_ir, self.root)

        cohort_path = cohort_ir["bindings"]["migration_dag"]["path"]
        self.assertTrue(cohort_path.startswith("project-ir-domain/cohort-dag-"))
        self.assertEqual(("base",), plan.accepted_group_ids)

        rejected = integration.integrate_rust_project_ir(
            cohort_ir, self.root, self.workspace / "partial-project",
        )
        self.assertEqual("failed", rejected["status"])
        self.assertEqual(
            "rust_project_ir_scope_not_full_project",
            rejected["diagnostics"][0]["code"],
        )

    def test_feature_and_cfg_are_rendered_from_ir(self) -> None:
        item = descriptor(self.root, "unit", "pub fn optional_value() {}\n")
        ir, _manifest = bound_ir(self.root, [item], {"unit": []})
        module = ir["modules"][0]
        evidence = module["evidence"]
        feature = {
            "feature_id": "feature-extra", "name": "extra", "default": False,
            "enables": [], "module_ids": [module["module_id"]], "evidence": evidence,
        }
        cfg = {
            "cfg_id": "cfg-unix", "expression": "unix",
            "module_ids": [module["module_id"]], "evidence": evidence,
        }
        configured = rebuild(ir, features=[feature], cfgs=[cfg])

        plan = reconstruct_cargo_project_from_ir(configured, self.root)

        cargo = plan.files["Cargo.toml"].decode("ascii")
        lib = plan.files["src/lib.rs"].decode("ascii")
        self.assertIn("extra = []", cargo)
        self.assertIn('#[cfg(all(unix, feature = "extra"))]', lib)

    def test_failed_ir_increment_preserves_managed_last_good(self) -> None:
        item = descriptor(self.root, "unit", "pub fn stable_value() -> i32 { 8 }\n")
        ir, _manifest = bound_ir(self.root, [item], {"unit": []})
        project = self.workspace / "managed"
        first = integration.integrate_rust_project_ir(ir, self.root, project)
        self.assertEqual("integrated", first["status"])
        generation = project / "generations" / first["generation"]["id"]
        before = {path.relative_to(generation): path.read_bytes()
                  for path in generation.rglob("*") if path.is_file()}
        broken = rebuild(ir, public_api=[])

        failed = integration.integrate_rust_project_ir(broken, self.root, project)

        self.assertEqual("failed", failed["status"])
        self.assertTrue(failed["last_good_preserved"])
        after = {path.relative_to(generation): path.read_bytes()
                 for path in generation.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_ir_hash_drift_is_rejected_before_filesystem_write(self) -> None:
        item = descriptor(self.root, "unit", "pub fn value() {}\n")
        ir, _manifest = bound_ir(self.root, [item], {"unit": []})
        ir["crate"]["edition"] = "2018"
        project = self.workspace / "unwritten"

        result = integration.integrate_rust_project_ir(ir, self.root, project)

        self.assertEqual("failed", result["status"])
        self.assertEqual("rust_project_ir_binding_invalid", result["diagnostics"][0]["code"])
        self.assertFalse(project.exists())

    def test_interface_completeness_cannot_be_promoted_by_the_caller(self) -> None:
        item = descriptor(self.root, "unit", "pub fn value() {}\n")
        ir, _manifest = bound_ir(self.root, [item], {"unit": []})
        self.assertEqual("partial", ir["interface_completeness"]["status"])
        self.assertIn(
            "public-signature", ir["interface_completeness"]["unresolved_sections"],
        )
        ir["interface_completeness"]["status"] = "complete"
        with self.assertRaisesRegex(
            cargo_project.ProjectInputError, "rust_project_ir_binding_invalid",
        ):
            reconstruct_cargo_project_from_ir(ir, self.root)

    def test_quarantine_rejects_same_count_different_ir_member(self) -> None:
        original = descriptor(self.root, "original", "pub fn original() {}\n")
        replacement = descriptor(self.root, "replacement", "pub fn replacement() {}\n")
        ir, _manifest = bound_ir(self.root, [original], {"original": []})
        members = [{
            "unit_id": "replacement",
            "artifact_id": replacement["artifact_id"],
            "content_sha256": replacement["sha256"],
        }]
        candidate_manifest = {"members": members}
        encoded = json.dumps(
            candidate_manifest, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        candidate_set = hashlib.sha256(encoded).hexdigest()

        result = quarantine_generation.materialize_rust_project_ir_quarantine_generation(
            ir, [replacement], self.root, self.workspace / "member-mismatch",
            candidate_set, candidate_manifest,
        )

        self.assertEqual("failed", result["status"])
        self.assertEqual(
            "quarantine_rust_project_ir_candidate_set_mismatch",
            result["diagnostics"][0]["code"],
        )


if __name__ == "__main__":
    unittest.main()
