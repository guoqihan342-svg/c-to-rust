from __future__ import annotations

import json
import unittest

from validation.tools._project_migration_harness.sandbox_diagnostics import (
    cargo_diagnostics,
)
from validation.tools._project_migration_harness.project_cargo_diagnostic_intake import (
    partition_cargo_diagnostics,
)


class ProjectMigrationCargoDiagnosticTests(unittest.TestCase):
    def test_workspace_module_location_is_preserved_without_host_path(self) -> None:
        digest = "a" * 64
        event = {
            "reason": "compiler-message",
            "message": {
                "level": "error",
                "code": {"code": "E0308"},
                "message": "mismatched types",
                "spans": [{
                    "is_primary": True,
                    "file_name": f"/workspace/src/unit_{digest}.rs",
                    "line_start": 7,
                    "column_start": 11,
                }],
            },
        }
        result = cargo_diagnostics(json.dumps(event) + "\n", "check")
        self.assertEqual(f"src/unit_{digest}.rs", result[0]["file"])
        self.assertEqual(7, result[0]["line"])
        self.assertEqual(11, result[0]["column"])
        self.assertEqual("error", result[0]["level"])
        self.assertEqual("rustc-compiler-message", result[0]["origin"])

    def test_non_workspace_or_traversal_location_is_withheld(self) -> None:
        for filename in ("/host/private/source.rs", "/workspace/src/../private.rs"):
            with self.subTest(filename=filename):
                event = {
                    "reason": "compiler-message",
                    "message": {
                        "level": "error",
                        "code": None,
                        "message": "failed",
                        "spans": [{
                            "is_primary": True,
                            "file_name": filename,
                            "line_start": 1,
                            "column_start": 1,
                        }],
                    },
                }
                result = cargo_diagnostics(json.dumps(event) + "\n", "check")
                self.assertNotIn("file", result[0])

    def test_warning_is_not_a_repair_diagnostic(self) -> None:
        event = {
            "reason": "compiler-message",
            "message": {
                "level": "warning", "code": {"code": "unused_imports"},
                "message": "unused import", "spans": [],
            },
        }
        self.assertEqual([], cargo_diagnostics(json.dumps(event), "check"))

    def test_error_overflow_fails_closed(self) -> None:
        event = {
            "reason": "compiler-message",
            "message": {
                "level": "error", "code": {"code": "E0308"},
                "message": "mismatched types", "spans": [],
            },
        }
        result = cargo_diagnostics(
            "\n".join(json.dumps(event) for _ in range(65)), "check",
        )
        self.assertEqual("cargo_diagnostic_overflow", result[0]["code"])
        self.assertNotIn("origin", result[0])

    def test_partition_uses_frozen_cohort_and_keeps_project_scope(self) -> None:
        digest = "a" * 64
        member = {
            "unit_id": "unit", "artifact_id": "candidate",
            "content_sha256": digest,
        }
        unit_error = _error("e0308", f"src/unit_{digest}.rs")
        project_error = _error("e0432", "src/lib.rs", "unresolved import `shared`")
        ir = {
            "public_api": [{"symbol": "shared", "module_id": "module-a"}],
            "shared_types": [], "global_ownership": [], "initialization": [],
            "ffi_boundaries": [], "features": [],
        }
        partition = partition_cargo_diagnostics(
            gate_kind="cargo-check",
            diagnostics=[unit_error, project_error],
            candidate_members=[member], rust_project_ir=ir,
        )
        self.assertIsNone(partition.admission_blocker)
        self.assertEqual([("unit", "candidate")], list(partition.unit_diagnostics))
        self.assertEqual(1, len(partition.project_diagnostics))
        project = partition.project_diagnostics[0]
        self.assertEqual("compile", project["family"])
        self.assertEqual(["module-a"], project["project_diagnostic"]["affected_module_ids"])

    def test_stale_or_ambiguous_unit_path_admits_nothing(self) -> None:
        partition = partition_cargo_diagnostics(
            gate_kind="cargo-check",
            diagnostics=[_error("e0308", f"src/unit_{'b' * 64}.rs")],
            candidate_members=[{
                "unit_id": "unit", "artifact_id": "candidate",
                "content_sha256": "a" * 64,
            }],
            rust_project_ir={},
        )
        self.assertEqual("unit-path-not-unique", partition.admission_blocker)
        self.assertEqual({}, partition.unit_diagnostics)
        self.assertEqual([], partition.project_diagnostics)


def _error(code: str, file: str, message: str = "mismatched types") -> dict:
    return {
        "code": code, "stage": "cargo-check", "message": message,
        "file": file, "line": 1, "column": 1, "level": "error",
        "origin": "rustc-compiler-message",
    }


if __name__ == "__main__":
    unittest.main()
