from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.rust_project_cargo_v3_projection import (
    derive_rust_project_cargo_v3_projection,
)
from validation.tools._project_migration_harness.rust_project_cargo_v3_render import (
    render_rust_project_cargo_v3_files,
)
from validation.tools._project_migration_harness.rust_project_cargo_v3_source_layout import (
    derive_rust_project_cargo_v3_source_layout,
)
from validation.tools._project_migration_harness.rust_project_ir_v3 import (
    build_rust_project_ir_v3,
)
from validation.tools._project_migration_harness.rust_project_ir_v3_topology_products import (
    input_occurrence_id,
)
from validation.tools._project_migration_harness.rust_project_ir_v3_validation import (
    module_id_for_target_candidate,
)
from validation.tools.project_migration_rust_project_ir_v3_link_test_support import (
    attach_link_expectation,
)


class RustProjectCargoV3OccurrenceOrderTests(unittest.TestCase):
    def test_explicit_occurrences_drive_projection_and_root_order(self) -> None:
        ir, sources, module_order = _ordered_binary_ir()
        layout = derive_rust_project_cargo_v3_source_layout(ir, sources)

        projection = derive_rust_project_cargo_v3_projection(ir, layout)
        files = render_rust_project_cargo_v3_files(ir, projection, sources)

        target = projection["targets"][0]
        self.assertEqual(module_order, target["module_ids"])
        self.assertEqual(ir["targets"][0]["input_occurrences"],
                         target["input_occurrences"])
        modules = {item["module_id"]: item for item in projection["modules"]}
        root = files[target["root_path"]]
        helper = f"mod {modules[module_order[1]]['identifier']};".encode()
        self.assertLess(root.index(b"include!("), root.index(helper))

        drifted = copy.deepcopy(projection)
        drifted["targets"][0]["module_ids"].reverse()
        payload = {key: value for key, value in drifted.items()
                   if key != "projection_sha256"}
        drifted["projection_sha256"] = content_sha256(payload)
        with self.assertRaisesRegex(ValueError, "module order drifted"):
            render_rust_project_cargo_v3_files(ir, drifted, sources)

        duplicate_id = copy.deepcopy(projection)
        occurrences = duplicate_id["targets"][0]["input_occurrences"]
        occurrences[1]["occurrence_id"] = occurrences[0]["occurrence_id"]
        payload = {key: value for key, value in duplicate_id.items()
                   if key != "projection_sha256"}
        duplicate_id["projection_sha256"] = content_sha256(payload)
        with self.assertRaisesRegex(ValueError, "occurrence_id_invalid"):
            render_rust_project_cargo_v3_files(ir, duplicate_id, sources)

    @unittest.skipUnless(shutil.which("cargo"), "cargo is unavailable")
    def test_occurrence_ordered_binary_passes_locked_offline_cargo(self) -> None:
        ir, sources, _module_order = _ordered_binary_ir()
        layout = derive_rust_project_cargo_v3_source_layout(ir, sources)
        projection = derive_rust_project_cargo_v3_projection(ir, layout)
        files = render_rust_project_cargo_v3_files(ir, projection, sources)
        with tempfile.TemporaryDirectory(prefix="cargo-v3-occurrence-") as root:
            project = Path(root)
            for relative, data in files.items():
                path = project.joinpath(*relative.split("/"))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            result = subprocess.run(
                ["cargo", "check", "--workspace", "--all-targets", "--locked", "--offline"],
                cwd=project, check=False, capture_output=True, text=True,
            )
        self.assertEqual(0, result.returncode, result.stderr)


def _ordered_binary_ir() -> tuple[dict, dict[str, bytes], list[str]]:
    sources = {
        "unit-entry": b"fn main() {}\n",
        "unit-helper": b"pub fn helper() {}\n",
    }
    shas = {key: hashlib.sha256(value).hexdigest() for key, value in sources.items()}
    build_sha, build_target = "d" * 64, "consumer-bin"
    modules = {}
    for unit_id in sorted(sources):
        source_id = f"source-{unit_id}"
        module_id = module_id_for_target_candidate(
            "namespace-bin", unit_id, shas[unit_id], [source_id],
        )
        modules[unit_id] = {
            "module_id": module_id, "package_id": "package-bin",
            "target_id": "target-bin", "target_namespace_id": "namespace-bin",
            "rust_path": f"packages/package-bin/src/{module_id}.rs",
            "unit_id": unit_id, "source_unit_ids": [source_id],
            "candidate_sha256": shas[unit_id], "visibility": "crate",
            "evidence": _evidence(build_sha, [unit_id], [shas[unit_id]]),
        }
    module_order = [modules["unit-entry"]["module_id"],
                    modules["unit-helper"]["module_id"]]
    evidence = _evidence(build_sha, sorted(sources), sorted(shas.values()))
    occurrences = [{
        "ordinal": ordinal,
        "occurrence_id": input_occurrence_id(build_sha, build_target, ordinal),
        "role": "link-input", "dependency_target_id": None,
        "object_target_id": f"object-{unit_id}",
        "source_unit_id": f"source-{unit_id}", "module_id": module_id,
        "binding_sha256": hashlib.sha256(f"binding-{unit_id}".encode()).hexdigest(),
    } for ordinal, (unit_id, module_id) in enumerate((
        ("unit-entry", module_order[0]), ("unit-helper", module_order[1]),
    ))]
    ref = lambda path, sha, size=1: {"path": path, "sha256": sha,
                                    "size_bytes": size}
    candidates = [{
        "unit_id": unit_id, "artifact_id": f"candidate-{unit_id}",
        "source": ref(f"candidates/{unit_id}.rs", shas[unit_id], len(sources[unit_id])),
    } for unit_id in sorted(sources)]
    target = {"target_id": "target-bin", "package_id": "package-bin",
              "name": "target_bin", "kind": "bin", "crate_types": ["bin"],
              "build_ir_target_id": build_target, "module_ids": module_order,
              "input_occurrences": occurrences, "ordered_link_arguments": [],
              "evidence": evidence}
    attach_link_expectation(target)
    ir = build_rust_project_ir_v3(
        migration_dag_ref=ref("plan/dag.json", "a" * 64),
        migration_graph_ref=ref("plan/graph.json", "b" * 64),
        build_ir_refs=[ref("plan/build.json", build_sha)], candidate_refs=candidates,
        workspace={"workspace_id": "workspace-bin", "resolver": "2",
                   "package_ids": ["package-bin"],
                   "default_package_ids": ["package-bin"], "evidence": evidence},
        packages=[{"package_id": "package-bin", "name": "package_bin",
                   "build_ir_target_id": build_target, "product_kind": "executable",
                   "dependency_package_ids": [], "target_ids": ["target-bin"],
                   "module_ids": module_order, "evidence": evidence}],
        targets=[target],
        modules=list(modules.values()),
    )
    return ir, sources, module_order


def _evidence(build: str, units: list[str], candidates: list[str]) -> dict:
    return {"build_ir_sha256s": [build], "dag_unit_ids": sorted(units),
            "candidate_sha256s": sorted(candidates)}


if __name__ == "__main__":
    unittest.main()
