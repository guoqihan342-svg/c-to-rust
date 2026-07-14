from __future__ import annotations

from pathlib import Path
import unittest


PACKAGE = Path(__file__).resolve().parent / "_project_migration_harness"
PRIVATE_MARKERS = {
    "meson_introspection",
    "meson_source_groups",
    "meson_target_id",
    "meson_target_type",
}
ALLOWED_MODULES = {
    "build_ir_meson.py",
    "generated_build_facts.py",
    "generated_closure.py",
}


class ProjectMigrationBuildIRAdapterBoundaryTests(unittest.TestCase):
    def test_downstream_modules_cannot_consume_meson_private_shapes(self) -> None:
        violations: list[str] = []
        for path in sorted(PACKAGE.glob("*.py")):
            if path.name in ALLOWED_MODULES or path.name.startswith("meson_"):
                continue
            text = path.read_text(encoding="utf-8")
            found = sorted(marker for marker in PRIVATE_MARKERS if marker in text)
            if found:
                violations.append(f"{path.name}: {', '.join(found)}")

        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
