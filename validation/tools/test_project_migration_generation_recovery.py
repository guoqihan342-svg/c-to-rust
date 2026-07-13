from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from validation.tools._project_migration_harness import integration
from validation.tools._project_migration_harness import integration_generation


class ProjectMigrationGenerationRecoveryTests(unittest.TestCase):
    def test_missing_projection_is_rebuilt_from_atomic_current(self) -> None:
        with tempfile.TemporaryDirectory(prefix="migration-generation-recover-") as temporary:
            root = Path(temporary)
            candidates = root / "candidates"
            candidates.mkdir()
            project = root / "project"
            descriptor = _descriptor(candidates, b"pub fn value() -> i32 { 1 }\n")

            result = integration.integrate_candidates(
                {"dag": {"unit": []}}, [descriptor], candidates, project,
            )
            expected = _snapshot(project)
            store = integration_generation.generation_store_root(project)
            current = json.loads((store / "CURRENT").read_text(encoding="ascii"))
            generation = store / "generations" / current["generation"]
            self.assertEqual(result["generation"]["id"], generation.name)
            self.assertTrue(generation.is_dir())

            shutil.rmtree(project)
            recovered = integration_generation.recover_current_generation(project)

            self.assertEqual(generation.resolve(), recovered)
            self.assertEqual(expected, _snapshot(project))
            self.assertFalse((store / "RECOVERY").exists())
            self.assertEqual([], list(root.glob(".project.last-good.*")))

    def test_restart_recovers_when_current_was_switched_before_projection(self) -> None:
        with tempfile.TemporaryDirectory(prefix="migration-generation-switch-") as temporary:
            root = Path(temporary)
            candidates = root / "candidates"
            candidates.mkdir()
            project = root / "project"
            first = _descriptor(candidates, b"pub fn value() -> i32 { 1 }\n")
            self.assertEqual(
                "integrated",
                integration.integrate_candidates(
                    {"dag": {"unit": []}}, [first], candidates, project,
                )["status"],
            )
            old_projection = _snapshot(project)
            second = _descriptor(candidates, b"pub fn value() -> i32 { 2 }\n")

            with mock.patch.object(
                integration_generation,
                "_synchronize_projection",
                side_effect=OSError("simulated process interruption"),
            ):
                interrupted = integration.integrate_candidates(
                    {"dag": {"unit": []}}, [second], candidates, project,
                )

            self.assertEqual("failed", interrupted["status"])
            self.assertEqual(
                "generation_projection_pending",
                interrupted["diagnostics"][0]["code"],
            )
            self.assertTrue(interrupted["last_good_preserved"])
            self.assertEqual(old_projection, _snapshot(project))

            generation = integration_generation.recover_current_generation(project)
            self.assertIsNotNone(generation)
            recovered = _snapshot(project)
            self.assertNotEqual(old_projection, recovered)
            self.assertIn(b"i32 { 2 }", b"".join(recovered.values()))
            state = json.loads(
                (integration_generation.generation_store_root(project) / "CURRENT")
                .read_text(encoding="ascii")
            )
            self.assertEqual(generation.name, state["generation"])


def _descriptor(root: Path, source: bytes) -> dict[str, object]:
    (root / "unit.rs").write_bytes(source)
    return {
        "group_id": "unit",
        "status": "accepted",
        "source_path": "unit.rs",
        "sha256": hashlib.sha256(source).hexdigest(),
        "public_symbols": ["value"],
        "required_symbols": [],
        "unsafe_count": 0,
    }


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


if __name__ == "__main__":
    unittest.main()
