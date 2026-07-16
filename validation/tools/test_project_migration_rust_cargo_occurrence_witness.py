from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.cargo_compiler_artifact_evidence import (
    parse_cargo_compiler_artifact_evidence,
)
from validation.tools._project_migration_harness.rust_cargo_occurrence_expectation import (
    derive_rust_cargo_occurrence_expectation,
)
from validation.tools._project_migration_harness.rust_cargo_occurrence_witness import (
    build_rust_cargo_occurrence_witness,
)
from validation.tools._project_migration_harness.rust_occurrence_manifest import (
    occurrence_manifest_bytes,
)
from validation.tools._project_migration_harness.rust_product_evidence import (
    persist_captured_rust_products,
)
from validation.tools._project_migration_harness.rust_project_cargo_v3_projection_analysis import (
    root_path,
)
from validation.tools._project_migration_harness.rust_project_cargo_v3_projection_validation import (
    module_identifier, package_member_path,
)
from validation.tools._project_migration_harness.rust_project_ir_v3 import (
    build_rust_project_ir_v3,
)
from validation.tools._project_migration_harness.rustc_dep_info_evidence import (
    persist_captured_rustc_dep_info,
)
from validation.tools.project_migration_rust_link_product_test_support import (
    ar_member, archive, relocatable_elf,
)
from validation.tools.test_project_migration_rust_project_ir_v3_topology import (
    ARTIFACT, _build, _candidate, _derive, _product, _ref, _scope, _unit,
)


class RustCargoOccurrenceWitnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="occurrence-witness-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "artifacts"
        (self.root / "state").mkdir(parents=True)
        self.ledger = self.root / "state" / "project-migration.sqlite3"
        self.ledger.write_bytes(b"")
        self.ir = _ir()
        self.expectation = derive_rust_cargo_occurrence_expectation(self.ir)
        self.target = self.ir["targets"][0]
        self.package = self.ir["packages"][0]
        self.compiler_target = {
            "kind": ["lib"], "crate_types": list(self.target["crate_types"]),
            "name": self.target["name"], "src_path": _root_path(self.target),
            "edition": "2021", "doc": False, "doctest": False, "test": False,
        }
        self.product_path = "/runtime/target/debug/libgeneric.a"

    def test_dep_info_and_final_archive_manifest_close_occurrences(self) -> None:
        products = self._products(with_manifest=True)
        dep_info = self._dep_info()
        witness = build_rust_cargo_occurrence_witness(
            self.ledger, self.expectation, self._compiler(), dep_info, products,
        )
        self.assertEqual("ready", witness["status"])
        self.assertTrue(witness["coverage"]["object_occurrence_coverage_complete"])
        product = witness["targets"][0]["products"][0]
        self.assertEqual(0, product["archive_member_ordinal"])

    def test_missing_product_manifest_blocks(self) -> None:
        witness = build_rust_cargo_occurrence_witness(
            self.ledger, self.expectation, self._compiler(), self._dep_info(),
            self._products(with_manifest=False),
        )
        self.assertEqual("blocked", witness["status"])
        self.assertIn(
            "rust_cargo_occurrence_product_manifest_missing",
            {item["code"] for item in witness["blockers"]},
        )

    def _compiler(self) -> dict:
        artifact = {
            "reason": "compiler-artifact",
            "package_id": _package_id(self.package["name"]),
            "manifest_path": f"/workspace/{self.package['name']}/Cargo.toml",
            "target": self.compiler_target,
            "profile": {
                "opt_level": "0", "debuginfo": 2, "debug_assertions": True,
                "overflow_checks": True, "test": False,
            },
            "features": [], "filenames": [self.product_path],
            "executable": None, "fresh": False,
        }
        raw = _json(artifact) + b"\n" + _json({
            "reason": "build-finished", "success": True,
        }) + b"\n"
        return parse_cargo_compiler_artifact_evidence(raw)

    def _products(self, *, with_manifest: bool) -> list[dict]:
        marker = occurrence_manifest_bytes(self.target) if with_manifest else b""
        data = archive(ar_member("unit.o/", relocatable_elf(suffix=marker)))
        execution = persist_captured_rust_products(
            {
                "status": "passed", "_captured_rust_products": [{
                    "package_id": _package_id(self.package["name"]),
                    "target": self.compiler_target, "product_kind": "staticlib",
                    "guest_path_sha256": _sha(self.product_path), "data": data,
                }],
            },
            out_root=self.root, required=True,
        )
        return execution["rust_products"]

    def _dep_info(self) -> list[dict]:
        module = self.ir["modules"][0]
        module_path = (
            f"/workspace/{package_member_path(self.target['package_id'])}"
            f"/src/modules/{module_identifier(module['module_id'])}.rs"
        )
        raw = (
            f"{self.product_path}: {_root_path(self.target)} {module_path}\n"
        ).encode("utf-8")
        execution = persist_captured_rustc_dep_info(
            {
                "status": "passed", "_captured_rustc_dep_info": [{
                    "package_id": _package_id(self.package["name"]),
                    "target": self.compiler_target,
                    "product_guest_path_sha256": _sha(self.product_path),
                    "dep_info_guest_path_sha256": _sha(
                        "/runtime/target/debug/libgeneric.d",
                    ),
                    "data": raw,
                }],
            },
            out_root=self.root, required=True,
        )
        return execution["rustc_dep_info"]


def _ir() -> dict:
    candidate = _candidate("unit")
    build = _build(
        [_unit("unit")], [_product("product", "archive", ["obj-unit"], [])],
    )
    topology = _derive(
        [build], {"unit": _scope("unit", ["product"], ["product"])},
        [candidate],
    )
    return build_rust_project_ir_v3(
        migration_dag_ref=_ref("plan/dag.json", "a" * 64),
        migration_graph_ref=_ref("plan/graph.json", "c" * 64),
        build_ir_refs=[_ref("plan/build.json", ARTIFACT)],
        candidate_refs=[candidate], workspace=topology["workspace"],
        packages=topology["packages"], targets=topology["targets"],
        modules=topology["modules"],
        topology_blockers=topology["topology_blockers"],
    )


def _root_path(target: dict) -> str:
    return f"/workspace/{root_path(target['package_id'], target['kind'])}"


def _package_id(name: str) -> str:
    return f"path+file:///workspace/{name}#{name}@0.0.0"


def _sha(value: str) -> str:
    import hashlib
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


if __name__ == "__main__":
    unittest.main()
