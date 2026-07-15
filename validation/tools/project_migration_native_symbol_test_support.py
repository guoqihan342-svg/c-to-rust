from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import (
    write_bytes_artifact, write_json_artifact,
)
from validation.tools._project_migration_harness.native_link_context import (
    build_native_link_context,
)
from validation.tools._project_migration_harness.native_link_model import (
    build_native_link_candidate,
)
from validation.tools._project_migration_harness.native_symbol_context import (
    build_native_symbol_context,
)
from validation.tools._project_migration_harness.native_symbol_model import (
    build_native_symbol_candidate,
)
from validation.tools._project_migration_harness.rust_project_ir import (
    build_rust_project_ir,
)
from validation.tools._project_migration_harness.rust_project_ir_validation import (
    module_id_for_candidate,
)
from validation.tools.project_migration_native_link_test_support import (
    materialize_native_build_ir,
)


class NativeSymbolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="native-symbol-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        _root, _database, self.build_ir, self.build_ref = (
            materialize_native_build_ir(
                self.base,
                "symbols",
                "/private/libalpha.so /different/libbeta.a",
            )
        )
        self.link_context = build_native_link_context(
            self.build_ir, self.build_ref, profile="competition",
        )
        self.link_candidate = self._link_candidate()
        self.rust_ir = self._rust_ir(self._ffi_boundaries())
        self.symbol_context = build_native_symbol_context(
            self.rust_ir, self.link_context, self.link_candidate,
        )

    def _link_candidate(self) -> dict:
        proposals = []
        for requirement in self.link_context["requirements"]:
            shared = requirement["library_format"] == "shared-library"
            name = requirement["portable_name"]
            stem = name.removeprefix("lib").split(".so", 1)[0].split(".a", 1)[0]
            proposals.append({
                "requirement_id": requirement["requirement_id"],
                "strategy": "rustc-link-lib",
                "rustc_link_name": stem,
                "rustc_link_kind": "dylib" if shared else "static",
            })
        return build_native_link_candidate(self.link_context, {
            "schema_version": 1,
            "artifact_kind": "native-link-model-response",
            "context_sha256": self.link_context["context_sha256"],
            "proposals": proposals,
        })

    def _rust_ir(self, ffi_boundaries: list[dict]) -> dict:
        dag_ref = write_json_artifact(
            self.base, "facts/migration-dag.json",
            {"schema_version": 1, "dag": {"unit": []}, "dag_order": ["unit"]},
        )
        source_ref = write_bytes_artifact(
            self.base, "candidates/unit.rs", b"pub fn translated() {}\n",
        )
        module_id = module_id_for_candidate(source_ref["sha256"])
        evidence = {
            "build_ir_sha256s": [self.build_ref["sha256"]],
            "dag_unit_ids": ["unit"],
            "candidate_sha256s": [source_ref["sha256"]],
        }
        records = [{**item, "module_id": module_id, "evidence": evidence}
                   for item in ffi_boundaries]
        return build_rust_project_ir(
            migration_dag_ref=dag_ref,
            build_ir_refs=[self.build_ref],
            candidate_refs=[{
                "unit_id": "unit", "artifact_id": "candidate-unit",
                "source": source_ref,
            }],
            crate={
                "crate_id": "translated-project", "edition": "2021",
                "crate_types": ["rlib"], "root_module_id": module_id,
                "targets": ["library"], "evidence": evidence,
            },
            modules=[{
                "module_id": module_id, "parent_module_id": None,
                "rust_path": "src/lib.rs", "unit_id": "unit",
                "candidate_sha256": source_ref["sha256"],
                "visibility": "crate", "evidence": evidence,
            }],
            ffi_boundaries=records,
            native_link_requirements=self.link_context["requirements"],
        )

    @staticmethod
    def _ffi_boundaries() -> list[dict]:
        return [
            {
                "declaration_id": "ffi-alpha-a", "symbol": "alpha_rust_a",
                "direction": "import", "abi": "C", "link_name": "alpha_open",
            },
            {
                "declaration_id": "ffi-alpha-b", "symbol": "alpha_rust_b",
                "direction": "import", "abi": "C", "link_name": "alpha_open",
            },
            {
                "declaration_id": "ffi-beta", "symbol": "beta_rust",
                "direction": "import-export", "abi": "C",
                "link_name": "beta_process",
            },
            {
                "declaration_id": "ffi-runtime", "symbol": "runtime_rust",
                "direction": "import", "abi": "C", "link_name": "runtime_alloc",
            },
            {
                "declaration_id": "ffi-export", "symbol": "exported_rust",
                "direction": "export", "abi": "C", "link_name": "project_export",
            },
        ]

    def response(self, *, beta_kind: str = "native-requirement") -> dict:
        by_name = {item["link_name"]: item for item in self.symbol_context["symbols"]}
        requirements = {
            item["portable_name"]: item["requirement_id"]
            for item in self.symbol_context["providers"]
        }
        assignments = [
            {
                "symbol_id": by_name["alpha_open"]["symbol_id"],
                "provider_kind": "native-requirement",
                "requirement_id": requirements["libalpha.so"],
            },
            {
                "symbol_id": by_name["beta_process"]["symbol_id"],
                "provider_kind": beta_kind,
                "requirement_id": (
                    requirements["libbeta.a"]
                    if beta_kind == "native-requirement" else None
                ),
            },
            {
                "symbol_id": by_name["runtime_alloc"]["symbol_id"],
                "provider_kind": "runtime",
                "requirement_id": None,
            },
        ]
        return {
            "schema_version": 1,
            "artifact_kind": "native-symbol-model-response",
            "context_sha256": self.symbol_context["context_sha256"],
            "assignments": assignments,
        }

    def symbol_candidate(self) -> dict:
        return build_native_symbol_candidate(
            self.symbol_context, self.response(),
        )
