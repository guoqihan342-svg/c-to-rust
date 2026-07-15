from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from validation.tools._project_migration_harness import integration
from validation.tools._project_migration_harness.artifacts import (
    content_sha256, write_json_artifact,
)
from validation.tools._project_migration_harness.build_ir import (
    finalize_build_ir, stable_build_id, target_record,
)
from validation.tools._project_migration_harness.build_ir_projection import target_closure
from validation.tools._project_migration_harness.rust_project_cargo import (
    reconstruct_cargo_project_from_ir,
)
from validation.tools._project_migration_harness.rust_project_ir_derivation import (
    derive_rust_project_ir_from_candidates,
)
from validation.tools._project_migration_harness.rust_project_ir_validation import (
    RustProjectIRError, interface_projection, reopen_rust_project_ir_bindings,
)
from validation.tools.project_migration_rust_project_test_support import (
    descriptor, valid_build_ir,
)
from validation.tools.test_project_migration_c_compilation_facts import (
    valid_compilation_bundle,
)


def targeted_build_ir(*, link_count: int = 1) -> dict:
    payload = valid_build_ir()
    unit = payload["translation_units"][0]
    unit["provenance"] = {
        "raw_fact_role": "discovery", "entry_index": 0,
        "entry_sha256": "3" * 64,
    }
    object_output = dict(unit["output"])
    object_id = stable_build_id(
        "target", {"kind": "object", "output": object_output["path"]},
    )
    object_target = target_record(
        object_id, object_output["path"], "object", [object_output],
        [{"ordinal": 0, "role": "source", "binding": dict(unit["source"]),
          "dependency_target_id": None}],
        [], [{"kind": "compile", "arguments": []}], [],
        {"raw_fact_role": "discovery", "unit_id": unit["unit_id"]},
    )
    archive_output = {
        "path": "build/library-output", "kind": "file", "materialized": False,
    }
    archive_id = stable_build_id(
        "target", {"kind": "archive", "output": archive_output["path"]},
    )
    archive = target_record(
        archive_id, archive_output["path"], "archive", [archive_output],
        [{"ordinal": 0, "role": "link-input", "binding": object_output,
          "dependency_target_id": object_id}],
        [object_id], [], [], {"raw_fact_role": "generated-build-closure"},
    )
    archive["archive_semantics"] = {"operation": "qc", "ranlib_passes": 0}
    targets = [object_target, archive]
    for index in range(link_count):
        output = {"path": f"build/executable-output-{index}",
                  "kind": "file", "materialized": False}
        target_id = stable_build_id(
            "target", {"kind": "link", "output": output["path"]},
        )
        targets.append(target_record(
            target_id, output["path"], "link", [output],
            [{"ordinal": 0, "role": "link-input", "binding": archive_output,
              "dependency_target_id": archive_id}],
            [archive_id], [], [], {"raw_fact_role": "generated-build-closure"},
        ))
    payload["targets"] = sorted(targets, key=lambda item: item["target_id"])
    payload["target_closure"] = target_closure(payload["targets"])
    return finalize_build_ir(payload)


def targeted_ir(
    root: Path, *, link_count: int = 1, bind_compilation_facts: bool = True,
) -> dict:
    candidates = [
        descriptor(root, "core", "pub fn value() -> i32 { 7 }\n"),
        descriptor(root, "application",
                   "fn main() { assert_eq!(crate::value(), 7); }\n"),
        descriptor(root, "verification",
                   "#[test]\nfn arbitrary_case() { assert_eq!(crate::value(), 7); }\n"),
    ]
    build_ir = targeted_build_ir(link_count=link_count)
    build_ref = write_json_artifact(
        root, "plan/targeted-build-ir.json", build_ir,
    )
    manifest = {
        "schema_version": 1, "profile": "competition",
        "dag": {"application": ["core"], "core": [],
                "verification": ["core"]},
        "dag_order": ["core", "application", "verification"],
        "unsafe_policy": {"allow_unsafe": True, "max_total": None,
                          "max_per_group": None},
        "claim_boundary": {"semantic_gate": False,
                           "translation_coverage_numerator": 0},
    }
    if bind_compilation_facts:
        facts_ref = write_json_artifact(
            root, "plan/targeted-c-compilation-facts.json",
            valid_compilation_bundle(
                build_ir["translation_units"][0], build_ir["semantic_sha256"],
            ),
        )
        manifest["c_compilation_facts"] = {
            "status": "bound", "artifact": facts_ref,
        }
    dag_ref = write_json_artifact(root, "plan/targeted-migration-dag.json", manifest)
    return derive_rust_project_ir_from_candidates(
        migration_manifest=manifest, migration_dag_ref=dag_ref,
        build_ir_refs=[build_ref], candidate_descriptors=candidates,
        artifact_root=root,
    )


class RustProjectCargoTopologyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="rust-cargo-topology-")
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.root = self.workspace / "artifacts"
        self.root.mkdir()

    def test_bound_facts_promote_library_bin_and_test_targets(self) -> None:
        ir = targeted_ir(self.root)
        self.assertEqual("complete", ir["interface_completeness"]["status"])
        self.assertEqual(["bin", "library", "test"], ir["crate"]["targets"])
        self.assertEqual(["rlib", "staticlib"], ir["crate"]["crate_types"])
        self.assertEqual("pub fn value ( ) -> i32", ir["public_api"][0]["signature"])
        binding = reopen_rust_project_ir_bindings(ir, self.root)
        self.assertTrue(binding["topology_verified"])

        plan = reconstruct_cargo_project_from_ir(ir, self.root)
        manifest = plan.last_good_manifest
        cargo_toml = plan.files["Cargo.toml"].decode("ascii")
        self.assertIn("[lib]", cargo_toml)
        self.assertIn("[[bin]]", cargo_toml)
        self.assertIn("[[test]]", cargo_toml)
        self.assertTrue({item["root_path"] for item in manifest["cargo_targets"]}
                        <= set(plan.files))

        project = self.workspace / "promoted-project"
        result = integration.integrate_rust_project_ir(ir, self.root, project)
        self.assertEqual("integrated", result["status"], result)
        self.assertFalse(result["semantic_gate"])
        cargo = shutil.which("cargo")
        if cargo is not None:
            environment = os.environ.copy()
            environment["CARGO_TARGET_DIR"] = str(self.workspace / "cargo-target")
            completed = subprocess.run(
                [cargo, "test", "--quiet", "--offline", "--all-targets"],
                cwd=project, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=60, check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stdout)

    def test_ambiguous_build_targets_remain_partial(self) -> None:
        ir = targeted_ir(self.root, link_count=2)
        self.assertEqual("partial", ir["interface_completeness"]["status"])
        binding = reopen_rust_project_ir_bindings(ir, self.root)
        self.assertFalse(binding["topology_verified"])
        self.assertIn("build_ir_binary_target_ambiguous",
                      binding["topology_blockers"])
        result = integration.integrate_rust_project_ir(
            ir, self.root, self.workspace / "ambiguous-project",
        )
        self.assertEqual("blocked", result["status"])

    def test_missing_compilation_facts_cannot_promote_topology(self) -> None:
        ir = targeted_ir(self.root, bind_compilation_facts=False)
        self.assertEqual("partial", ir["interface_completeness"]["status"])
        binding = reopen_rust_project_ir_bindings(ir, self.root)
        self.assertFalse(binding["topology_verified"])
        self.assertIn(
            "c_compilation_facts_incomplete", binding["topology_blockers"],
        )

    def test_rehashed_interface_forgery_fails_reopen(self) -> None:
        ir = targeted_ir(self.root)
        forged = deepcopy(ir)
        forged["public_api"][0]["signature"] = "pub fn value ( ) -> u64"
        forged["interface_sha256"] = content_sha256(interface_projection(forged))
        forged["ir_sha256"] = content_sha256({
            key: value for key, value in forged.items() if key != "ir_sha256"
        })
        with self.assertRaisesRegex(RustProjectIRError, "public interface drifted"):
            reopen_rust_project_ir_bindings(forged, self.root)

    def test_rehashed_unbound_feature_fails_reopen(self) -> None:
        ir = targeted_ir(self.root)
        forged = deepcopy(ir)
        module = forged["modules"][0]
        forged["features"] = [{
            "feature_id": "feature-unbound", "name": "unbound",
            "default": False, "enables": [],
            "module_ids": [module["module_id"]], "evidence": module["evidence"],
        }]
        forged["interface_sha256"] = content_sha256(interface_projection(forged))
        forged["ir_sha256"] = content_sha256({
            key: value for key, value in forged.items() if key != "ir_sha256"
        })
        with self.assertRaisesRegex(RustProjectIRError, "unbound derived interface"):
            reopen_rust_project_ir_bindings(forged, self.root)


if __name__ == "__main__":
    unittest.main()
