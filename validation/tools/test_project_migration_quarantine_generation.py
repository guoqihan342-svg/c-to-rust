from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest

from validation.tools._project_migration_harness import cargo_project
from validation.tools import project_migration_legacy_cargo_test_support as integration
from validation.tools._project_migration_harness import integration_generation
from validation.tools import project_migration_legacy_quarantine_test_support as quarantine_generation


def _descriptor(
    root: Path, unit_id: str, group_id: str, filename: str, source: bytes,
    *, public: list[str], required: list[str] | None = None,
) -> dict[str, object]:
    (root / filename).write_bytes(source)
    return {
        "unit_id": unit_id,
        "artifact_id": f"artifact-{unit_id}",
        "group_id": group_id,
        "status": "accepted",
        "source_path": filename,
        "sha256": hashlib.sha256(source).hexdigest(),
        "public_symbols": public,
        "required_symbols": required or [],
        "unsafe_count": 0,
    }


def _candidate_set(descriptors: list[dict[str, object]]) -> tuple[dict, str]:
    members = sorted(({
        "unit_id": item["unit_id"],
        "artifact_id": item["artifact_id"],
        "content_sha256": item["sha256"],
    } for item in descriptors), key=lambda item: str(item["unit_id"]))
    manifest = {
        "schema_version": 2, "scope": "wave-provisional",
        "run_context_sha256": hashlib.sha256(b"run-context").hexdigest(),
        "dag_sha256": hashlib.sha256(b"dag").hexdigest(),
        "integration_manifest_sha256": hashlib.sha256(b"manifest").hexdigest(),
        "roots": sorted(str(item["unit_id"]) for item in descriptors),
        "members": members,
    }
    data = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return manifest, hashlib.sha256(data).hexdigest()


def _snapshot(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*") if path.is_file()
    }


class ProjectMigrationQuarantineGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="migration-quarantine-")
        self.root = Path(self.temporary.name)
        self.candidates = self.root / "candidates"
        self.candidates.mkdir()
        self.quarantine = self.root / "quarantine"
        self.first = _descriptor(
            self.candidates, "unit-1", "group-1", "one.rs",
            b"pub fn base_value() -> i32 { 4 }\n", public=["base_value"],
        )
        self.second = _descriptor(
            self.candidates, "unit-2", "group-2", "two.rs",
            b"pub fn final_value() -> i32 { crate::base_value() }\n",
            public=["final_value"], required=["base_value"],
        )
        self.descriptors = [self.second, self.first]
        self.manifest = {
            "dag": {"group-1": [], "group-2": ["group-1"]},
            "dag_order": ["group-1", "group-2"],
        }
        self.candidate_set_manifest, self.candidate_set = _candidate_set(self.descriptors)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _materialize(self, root: Path | None = None) -> dict[str, object]:
        return quarantine_generation.materialize_quarantine_generation(
            self.manifest, self.descriptors, self.candidates,
            root or self.quarantine, self.candidate_set,
            self.candidate_set_manifest,
        )

    def test_materializes_bound_read_only_generation_without_pointer(self) -> None:
        result = self._materialize()

        self.assertEqual("materialized", result["status"])
        self.assertEqual(2, result["candidate_count"])
        self.assertEqual(self.candidate_set, result["candidate_set"]["sha256"])
        self.assertFalse(result["last_good_updated"])
        self.assertFalse(result["cargo_executed"])
        generation = self.quarantine / result["generation"]["path"]
        self.assertEqual(
            result["generation"]["sha256"],
            hashlib.sha256((generation / cargo_project.LAST_GOOD_MANIFEST).read_bytes()).hexdigest(),
        )
        payload = json.loads(
            (generation / quarantine_generation.QUARANTINE_MANIFEST).read_text("utf-8")
        )
        self.assertEqual(self.candidate_set, payload["candidate_set"]["sha256"])
        self.assertEqual(2, len(payload["candidate_set"]["manifest"]["members"]))
        self.assertEqual("detached-cargo-quarantine", payload["kind"])
        self.assertFalse(payload["last_good_updated"])
        generated = json.loads(
            (generation / cargo_project.LAST_GOOD_MANIFEST).read_text("utf-8")
        )
        self.assertEqual("detached-quarantine", generated["generation_kind"])
        self.assertFalse((generation / "CURRENT").exists())
        self.assertFalse((self.quarantine / "CURRENT").exists())
        self.assertFalse((self.quarantine / "RECOVERY").exists())
        self.assertFalse((generation / "Cargo.toml").stat().st_mode & stat.S_IWUSR)

    def test_repeated_materialization_is_idempotent(self) -> None:
        first = self._materialize()
        second = self._materialize()

        self.assertEqual(first, second)
        entries = list((self.quarantine / "generations").iterdir())
        self.assertEqual([first["generation"]["sha256"]], [item.name for item in entries])
        self.assertFalse(any(item.name.startswith(".staging.") for item in entries))

    def test_candidate_drift_fails_without_changing_published_generation(self) -> None:
        first = self._materialize()
        before = _snapshot(self.quarantine)
        (self.candidates / "one.rs").write_bytes(b"pub fn changed() {}\n")

        result = self._materialize()

        self.assertEqual("failed", result["status"])
        self.assertEqual("candidate_hash_mismatch", result["diagnostics"][0]["code"])
        self.assertEqual(before, _snapshot(self.quarantine))
        self.assertTrue(first["generation"]["immutable"])

    def test_generation_collision_is_reverified_and_not_overwritten(self) -> None:
        first = self._materialize()
        generation = self.quarantine / first["generation"]["path"]
        cargo = generation / "Cargo.toml"
        cargo.chmod(0o600)
        cargo.write_bytes(b"collision\n")

        result = self._materialize()

        self.assertEqual("failed", result["status"])
        self.assertEqual("quarantine_generation_collision", result["diagnostics"][0]["code"])
        self.assertEqual(b"collision\n", cargo.read_bytes())
        self.assertFalse(any(
            item.name.startswith(".staging.")
            for item in (self.quarantine / "generations").iterdir()
        ))

    def test_candidate_set_digest_cannot_be_substituted(self) -> None:
        result = quarantine_generation.materialize_quarantine_generation(
            self.manifest, self.descriptors, self.candidates,
            self.quarantine, "0" * 64, self.candidate_set_manifest,
        )

        self.assertEqual("failed", result["status"])
        self.assertEqual("candidate_set_sha256_mismatch", result["diagnostics"][0]["code"])
        self.assertFalse(self.quarantine.exists())

    def test_quarantine_never_touches_managed_last_good(self) -> None:
        project = self.root / "managed-project"
        integrated = integration.integrate_candidates(
            self.manifest, self.descriptors, self.candidates, project,
        )
        self.assertEqual("integrated", integrated["status"])
        store = integration_generation.generation_store_root(project)
        before_project = _snapshot(project)
        before_store = _snapshot(store)

        result = self._materialize()

        self.assertEqual("materialized", result["status"])
        self.assertEqual(before_project, _snapshot(project))
        self.assertEqual(before_store, _snapshot(store))
        rejected = self._materialize(project)
        self.assertEqual("quarantine_root_not_dedicated", rejected["diagnostics"][0]["code"])
        self.assertEqual(before_project, _snapshot(project))
        self.assertEqual(before_store, _snapshot(store))

    def test_overlapping_and_link_roots_are_rejected(self) -> None:
        nested = self.candidates / "quarantine"
        overlap = self._materialize(nested)
        self.assertEqual("quarantine_root_overlaps_candidates", overlap["diagnostics"][0]["code"])
        self.assertFalse(nested.exists())

        outside = self.root / "outside"
        outside.mkdir()
        linked = self.root / "linked-quarantine"
        try:
            linked.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlink unavailable: {error}")
        result = self._materialize(linked)
        self.assertEqual("quarantine_root_untrusted", result["diagnostics"][0]["code"])
        self.assertEqual({}, _snapshot(outside))

        linked_parent = self.root / "linked-parent"
        linked_parent.symlink_to(outside, target_is_directory=True)
        nested_result = self._materialize(linked_parent / "nested")
        self.assertEqual(
            "quarantine_root_untrusted", nested_result["diagnostics"][0]["code"]
        )
        linked_candidates = self.root / "linked-candidates"
        linked_candidates.symlink_to(self.candidates, target_is_directory=True)
        candidate_result = quarantine_generation.materialize_quarantine_generation(
            self.manifest, self.descriptors, linked_candidates,
            self.root / "other-quarantine", self.candidate_set,
            self.candidate_set_manifest,
        )
        self.assertEqual(
            "candidate_root_untrusted", candidate_result["diagnostics"][0]["code"]
        )


if __name__ == "__main__":
    unittest.main()
