from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.c_index import index_translation_units


class ProjectMigrationMacroDefinitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="project-macro-definition-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_header_function_macro_definition_is_boundary_not_fake_function(self) -> None:
        self.unit(
            "include/test_api.h",
            "#define TEST_CASE(name) void name(void)\n",
            "header-only",
        )
        unit = self.unit(
            "src/test_api.c",
            '#include "test_api.h"\n'
            "int ordinary(void) { return 7; }\n"
            "TEST_CASE(first_case) { (void)ordinary(); }\n",
            "test-api-variant",
        )
        unit["includes"] = [
            {"kind": "user", "scope": "repository", "path": "include"}
        ]

        index = index_translation_units(self.root, [unit])

        self.assertEqual("ready_with_boundaries", index["status"])
        self.assertEqual(["ordinary"], [item["symbol"] for item in index["nodes"]])
        self.assertNotIn("TEST_CASE", {item["symbol"] for item in index["nodes"]})
        self.assertIn(
            "function_like_macro_definition_unsupported",
            {item["kind"] for item in index["parser"]["blockers"]},
        )
        source_context = index["unit_contexts"][0]["top_level"]["source"]["content"]
        self.assertIn("TEST_CASE(first_case)", source_context)

    def unit(self, relative: str, source: str, unit_id: str) -> dict:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = source.encode("utf-8")
        path.write_bytes(raw)
        return {
            "unit_id": unit_id,
            "source": {"path": relative, "sha256": hashlib.sha256(raw).hexdigest()},
        }


if __name__ == "__main__":
    unittest.main()
