from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from validation.tools.project_migration_rust_project_cargo_v3_test_support import (
    V3CargoFixture, direct_two_package_ir,
)
from validation.tools._project_migration_harness import cargo_project
from validation.tools._project_migration_harness.integration_validation import (
    existing_state,
)
from validation.tools._project_migration_harness.project_rust_ir import (
    derive_bound_project_ir,
)
from validation.tools._project_migration_harness.rust_project_cargo import (
    V3_GENERATOR, reconstruct_cargo_project_from_ir,
)
from validation.tools._project_migration_harness.rust_project_cargo_v3_projection import (
    derive_rust_project_cargo_v3_projection,
)
from validation.tools._project_migration_harness.rust_project_cargo_v3_render import (
    PROJECTION_FILE, render_rust_project_cargo_v3_files,
)
from validation.tools._project_migration_harness.rust_project_cargo_v3_source_layout import (
    derive_rust_project_cargo_v3_source_layout,
)


class RustProjectCargoV3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="cargo-v3-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "artifacts"
        self.root.mkdir()
        self.fixture = V3CargoFixture(self.root)
        self.addCleanup(self.fixture.close)

    def test_static_library_reconstructs_deterministically_and_reopens(self) -> None:
        ir = self.fixture.build("pub fn value() -> i32 { 7 }\n")

        first = reconstruct_cargo_project_from_ir(ir, self.root)
        second = reconstruct_cargo_project_from_ir(copy.deepcopy(ir), self.root)

        self.assertEqual(first.files, second.files)
        self.assertEqual(V3_GENERATOR, first.last_good_manifest["generator"])
        self.assertIn("Cargo.toml", first.files)
        self.assertIn(PROJECTION_FILE, first.files)
        self.assertEqual(["group-a"], list(first.accepted_group_ids))
        project = Path(self.temporary.name) / "project"
        self._materialize(project, first.files)
        _state, managed = existing_state(project)
        self.assertTrue(managed)
        projection = json.loads(first.files[PROJECTION_FILE])
        self.assertEqual("ready", projection["status"])
        self.assertFalse(first.last_good_manifest["semantic_gate"])

    def test_full_target_scoped_production_domain_selects_v3(self) -> None:
        self.fixture.build("pub fn value() -> i32 { 7 }\n")

        ir = derive_bound_project_ir(
            migration_contract={"integration_manifest": self.fixture.dag_ref},
            migration_manifest=self.fixture.manifest,
            candidate_descriptors=[self.fixture.descriptor],
            artifact_root=self.root,
        )

        self.assertEqual(3, ir["schema_version"])
        self.assertNotIn("crate", ir)

    def test_development_domain_keeps_v2_compatibility(self) -> None:
        self.fixture.build("pub fn value() -> i32 { 7 }\n")
        manifest = copy.deepcopy(self.fixture.manifest)
        manifest["profile"] = "development"

        ir = derive_bound_project_ir(
            migration_contract={"integration_manifest": self.fixture.dag_ref},
            migration_manifest=manifest,
            candidate_descriptors=[self.fixture.descriptor],
            artifact_root=self.root,
        )

        self.assertEqual(2, ir["schema_version"])

    @unittest.skipUnless(shutil.which("cargo"), "cargo is unavailable")
    def test_library_workspace_passes_locked_offline_metadata_and_check(self) -> None:
        ir = self.fixture.build("pub fn value() -> i32 { 7 }\n")
        plan = reconstruct_cargo_project_from_ir(ir, self.root)
        project = Path(self.temporary.name) / "cargo-live"
        self._materialize(project, plan.files)

        metadata = subprocess.run(
            ["cargo", "metadata", "--locked", "--offline", "--format-version", "1"],
            cwd=project, check=False, capture_output=True, text=True,
        )
        check = subprocess.run(
            ["cargo", "check", "--workspace", "--all-targets", "--locked", "--offline"],
            cwd=project, check=False, capture_output=True, text=True,
        )

        self.assertEqual(0, metadata.returncode, metadata.stderr)
        self.assertEqual(0, check.returncode, check.stderr)

    def test_binary_requires_one_unguarded_main(self) -> None:
        missing = self.fixture.build("pub fn value() -> i32 { 7 }\n", product="link")
        with self.assertRaisesRegex(
            cargo_project.ProjectInputError, "binary_main_missing",
        ):
            reconstruct_cargo_project_from_ir(missing, self.root)

        ready = self.fixture.build("fn main() {}\n", product="link")
        plan = reconstruct_cargo_project_from_ir(ready, self.root)
        roots = [path for path in plan.files if path.endswith("/src/main.rs")]
        self.assertEqual(1, len(roots))
        self.assertIn(b"include!", plan.files[roots[0]])

    def test_ordered_link_arguments_block_before_render(self) -> None:
        ir = self.fixture.build(
            "fn main() {}\n", product="link", link_arguments=("-lvalue",),
        )

        with self.assertRaisesRegex(
            cargo_project.ProjectInputError, "link_occurrence_order_unproven",
        ):
            reconstruct_cargo_project_from_ir(ir, self.root)

    def test_shared_product_flag_is_consumed_by_cdylib_crate_type(self) -> None:
        ir = self.fixture.build(
            "pub fn shared_value() -> i32 { 9 }\n",
            product="link", link_arguments=("-shared",),
        )

        plan = reconstruct_cargo_project_from_ir(ir, self.root)

        target = plan.last_good_manifest["cargo_targets"][0]
        self.assertEqual("cdylib", target["kind"])
        self.assertEqual(["cdylib"], target["crate_types"])

    def test_two_independent_packages_render_in_one_workspace(self) -> None:
        ir, sources = direct_two_package_ir()
        layout = derive_rust_project_cargo_v3_source_layout(ir, sources)
        projection = derive_rust_project_cargo_v3_projection(ir, layout)

        files = render_rust_project_cargo_v3_files(ir, projection, sources)

        self.assertEqual("ready", projection["status"])
        self.assertEqual(2, len(projection["packages"]))
        self.assertIn("packages/package-bin/Cargo.toml", files)
        self.assertIn("packages/package-lib/Cargo.toml", files)
        self.assertEqual(4, files["Cargo.toml"].count(b'"packages/package-'))
        bin_manifest = files["packages/package-bin/Cargo.toml"]
        lib_manifest = files["packages/package-lib/Cargo.toml"]
        self.assertIn(b"test = false", bin_manifest)
        self.assertIn(b"bench = false", bin_manifest)
        self.assertIn(b"test = false", lib_manifest)
        self.assertIn(b"doctest = false", lib_manifest)
        self.assertIn(b"bench = false", lib_manifest)

    @unittest.skipUnless(shutil.which("cargo"), "cargo is unavailable")
    def test_two_package_workspace_passes_locked_offline_cargo(self) -> None:
        ir, sources = direct_two_package_ir()
        layout = derive_rust_project_cargo_v3_source_layout(ir, sources)
        projection = derive_rust_project_cargo_v3_projection(ir, layout)
        files = render_rust_project_cargo_v3_files(ir, projection, sources)
        project = Path(self.temporary.name) / "cargo-two-package"
        self._materialize(project, files)

        metadata = subprocess.run(
            ["cargo", "metadata", "--locked", "--offline", "--format-version", "1"],
            cwd=project, check=False, capture_output=True, text=True,
        )
        check = subprocess.run(
            ["cargo", "check", "--workspace", "--all-targets", "--locked", "--offline"],
            cwd=project, check=False, capture_output=True, text=True,
        )

        self.assertEqual(0, metadata.returncode, metadata.stderr)
        self.assertEqual(2, len(json.loads(metadata.stdout)["packages"]))
        self.assertEqual(0, check.returncode, check.stderr)

    def test_source_layout_rejects_cfg_guarded_main(self) -> None:
        ir = self.fixture.build('#[cfg(feature = "x")]\nfn main() {}\n', product="link")
        source = (self.root / "candidates/link.rs").read_bytes()

        layout = derive_rust_project_cargo_v3_source_layout(
            ir, {"group-a": source},
        )

        self.assertEqual("blocked", layout["status"])
        self.assertIn(
            "rust_project_cargo_main_cfg_unresolved",
            {item["code"] for item in layout["blockers"]},
        )

    def test_projection_hash_drift_is_rejected(self) -> None:
        ir = self.fixture.build("pub fn value() -> i32 { 7 }\n")
        source = (self.root / "candidates/archive.rs").read_bytes()
        layout = derive_rust_project_cargo_v3_source_layout(
            ir, {"group-a": source},
        )
        projection = derive_rust_project_cargo_v3_projection(ir, layout)
        projection["packages"][0]["name"] = "forged"

        with self.assertRaisesRegex(ValueError, "hash drifted"):
            render_rust_project_cargo_v3_files(
                ir, projection, {"group-a": source},
            )

    @staticmethod
    def _materialize(root: Path, files) -> None:
        for relative, data in files.items():
            path = root.joinpath(*relative.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

if __name__ == "__main__":
    unittest.main()
