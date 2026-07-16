from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness import cargo_project
from validation.tools._project_migration_harness.integration_validation import (
    existing_state,
)
from validation.tools._project_migration_harness.rust_project_cargo import (
    GENERATOR, SUPPORTED_GENERATORS, V3_GENERATOR,
    generator_for_rust_project_ir,
)


class RustProjectCargoGeneratorTests(unittest.TestCase):
    def test_generator_is_selected_only_by_ir_schema(self) -> None:
        self.assertEqual(GENERATOR, generator_for_rust_project_ir({
            "schema_version": 2,
        }))
        self.assertEqual(V3_GENERATOR, generator_for_rust_project_ir({
            "schema_version": 3,
        }))
        self.assertEqual({GENERATOR, V3_GENERATOR}, set(SUPPORTED_GENERATORS))
        with self.assertRaisesRegex(ValueError, "schema_version_unsupported"):
            generator_for_rust_project_ir({"schema_version": 4})

    def test_existing_state_accepts_only_fixed_v3_generator(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargo-generator-v3-") as name:
            root = Path(name)
            manifest = {
                "schema_version": cargo_project.SCHEMA_VERSION,
                "generator": V3_GENERATOR,
                "files": [],
            }
            (root / cargo_project.LAST_GOOD_MANIFEST).write_bytes(
                cargo_project.canonical_json_bytes(manifest),
            )

            _state, managed = existing_state(root)

            self.assertTrue(managed)

    def test_existing_state_rejects_unknown_generator(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargo-generator-unknown-") as name:
            root = Path(name)
            manifest = {
                "schema_version": cargo_project.SCHEMA_VERSION,
                "generator": "model-selected-generator",
                "files": [],
            }
            (root / cargo_project.LAST_GOOD_MANIFEST).write_bytes(
                cargo_project.canonical_json_bytes(manifest),
            )

            with self.assertRaisesRegex(
                cargo_project.ProjectInputError, "last_good_manifest_invalid",
            ):
                existing_state(root)


if __name__ == "__main__":
    unittest.main()
