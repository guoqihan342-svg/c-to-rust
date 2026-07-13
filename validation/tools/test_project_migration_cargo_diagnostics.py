from __future__ import annotations

import json
import unittest

from validation.tools._project_migration_harness.sandbox_diagnostics import (
    cargo_diagnostics,
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


if __name__ == "__main__":
    unittest.main()
