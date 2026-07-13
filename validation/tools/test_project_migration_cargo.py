from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness import cargo_project
from validation.tools._project_migration_harness import integration


def _sha(source: bytes) -> str:
    return hashlib.sha256(source).hexdigest()


def _descriptor(
    root: Path,
    group_id: str,
    filename: str,
    source: bytes,
    *,
    public_symbols: list[str],
    required_symbols: list[str] | None = None,
    unsafe_count: int = 0,
    status: str = "accepted",
) -> dict[str, object]:
    (root / filename).write_bytes(source)
    return {
        "group_id": group_id,
        "status": status,
        "source_path": filename,
        "sha256": _sha(source),
        "public_symbols": public_symbols,
        "required_symbols": required_symbols or [],
        "unsafe_count": unsafe_count,
    }


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


class ProjectMigrationCargoTests(unittest.TestCase):
    def test_reconstruction_is_stable_and_module_names_are_content_derived(self) -> None:
        with tempfile.TemporaryDirectory(prefix="migration-cargo-") as temporary:
            root = Path(temporary) / "candidates"
            root.mkdir()
            base = _descriptor(
                root, "arbitrary-left", "left.rs",
                b"pub fn source_value() -> i32 { 7 }\n",
                public_symbols=["source_value"],
            )
            leaf = _descriptor(
                root, "arbitrary-right", "right.rs",
                b"pub fn derived_value() -> i32 { crate::source_value() + 1 }\n",
                public_symbols=["derived_value"], required_symbols=["source_value"],
            )
            manifest = {
                "groups": [
                    {"group_id": "arbitrary-right", "dependencies": ["arbitrary-left"]},
                    {"group_id": "arbitrary-left", "dependencies": []},
                ],
                "waves": [
                    {"group_ids": ["arbitrary-left"]},
                    {"group_ids": ["arbitrary-right"]},
                ],
            }

            first = integration.reconstruct_cargo_project(manifest, [leaf, base], root)
            second = integration.reconstruct_cargo_project(manifest, [base, leaf], root)

            self.assertEqual(first.files, second.files)
            lib = first.files["src/lib.rs"].decode("ascii")
            for descriptor in (base, leaf):
                module = f"unit_{descriptor['sha256']}"
                self.assertIn(f"mod {module};", lib)
                self.assertIn(f"src/{module}.rs", first.files)
            self.assertNotIn("arbitrary-left", lib)
            self.assertNotIn("arbitrary-right", lib)

    def test_identity_renaming_does_not_change_generated_rust_tree(self) -> None:
        with tempfile.TemporaryDirectory(prefix="migration-rename-") as temporary:
            root = Path(temporary) / "candidates"
            root.mkdir()
            first = _descriptor(
                root, "node-a", "a.rs", b"pub fn input_term() -> i32 { 3 }\n",
                public_symbols=["input_term"],
            )
            second = _descriptor(
                root, "node-b", "b.rs",
                b"pub fn output_term() -> i32 { crate::input_term() }\n",
                public_symbols=["output_term"], required_symbols=["input_term"],
            )
            renamed = [dict(first, group_id="unit-x"), dict(second, group_id="unit-y")]
            original_plan = integration.reconstruct_cargo_project(
                {"dag": {"node-a": [], "node-b": ["node-a"]}, "dag_order": ["node-a", "node-b"]},
                [first, second], root,
            )
            renamed_plan = integration.reconstruct_cargo_project(
                {"dag": {"unit-x": [], "unit-y": ["unit-x"]}, "dag_order": ["unit-x", "unit-y"]},
                renamed, root,
            )
            generated = [path for path in original_plan.files if path != cargo_project.LAST_GOOD_MANIFEST]
            self.assertEqual(
                {path: original_plan.files[path] for path in generated},
                {path: renamed_plan.files[path] for path in generated},
            )

    def test_integration_records_dag_symbols_and_unsafe_policy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="migration-integrate-") as temporary:
            root = Path(temporary)
            candidates = root / "candidates"
            candidates.mkdir()
            project = root / "project"
            base = _descriptor(
                candidates, "stage-1", "one.rs", b"pub fn base_term() -> i32 { 1 }\n",
                public_symbols=["base_term"],
            )
            leaf = _descriptor(
                candidates, "stage-2", "two.rs",
                b"pub fn final_term() -> i32 { crate::base_term() }\n",
                public_symbols=["final_term"], required_symbols=["base_term"], unsafe_count=1,
            )
            manifest = {
                "dag": {"stage-1": [], "stage-2": ["stage-1"]},
                "dag_order": ["stage-1", "stage-2"],
                "unsafe_policy": {"allow_unsafe": True, "max_total": 1, "max_per_group": 1},
            }

            result = integration.integrate_candidates(manifest, [leaf, base], candidates, project)

            self.assertEqual("integrated", result["status"])
            self.assertFalse(result["cargo_executed"])
            self.assertEqual(["stage-1", "stage-2"], result["integrated_group_ids"])
            self.assertTrue((project / "Cargo.toml").is_file())
            self.assertTrue((project / "src" / "lib.rs").is_file())
            recorded = json.loads((project / cargo_project.LAST_GOOD_MANIFEST).read_text("utf-8"))
            self.assertEqual(1, recorded["unsafe_policy"]["observed_total"])
            self.assertEqual("satisfied", recorded["unsafe_policy"]["status"])
            self.assertFalse(recorded["cargo_executed"])

    def test_failed_increment_preserves_the_complete_last_good_tree(self) -> None:
        with tempfile.TemporaryDirectory(prefix="migration-last-good-") as temporary:
            root = Path(temporary)
            candidates = root / "candidates"
            candidates.mkdir()
            project = root / "project"
            first = _descriptor(
                candidates, "part-one", "one.rs", b"pub fn initial_term() -> i32 { 2 }\n",
                public_symbols=["initial_term"],
            )
            initial_manifest = {"dag": {"part-one": []}, "dag_order": ["part-one"]}
            self.assertEqual(
                "integrated",
                integration.integrate_candidates(initial_manifest, [first], candidates, project)["status"],
            )
            second = _descriptor(
                candidates, "part-two", "two.rs",
                b"pub fn next_term() -> i32 { crate::initial_term() } // ORACLE_SECRET\n",
                public_symbols=["next_term"], required_symbols=["initial_term"],
            )
            expanded_manifest = {
                "dag": {"part-one": [], "part-two": ["part-one"]},
                "dag_order": ["part-one", "part-two"],
            }
            self.assertEqual(
                "integrated",
                integration.integrate_candidates(expanded_manifest, [first, second], candidates, project)["status"],
            )
            last_good = _snapshot(project)
            invalid = dict(second, sha256="0" * 64)

            result = integration.integrate_candidates(
                expanded_manifest, [first, invalid], candidates, project,
            )

            self.assertEqual("failed", result["status"])
            self.assertTrue(result["last_good_preserved"])
            self.assertEqual("candidate_hash_mismatch", result["diagnostics"][0]["code"])
            self.assertEqual(last_good, _snapshot(project))
            serialized = json.dumps(result)
            self.assertNotIn("ORACLE_SECRET", serialized)
            self.assertNotIn(str(root), serialized)
            self.assertLess(len(serialized), 1_024)

    def test_rejected_candidate_paths_are_still_confined_and_verified(self) -> None:
        with tempfile.TemporaryDirectory(prefix="migration-path-") as temporary:
            root = Path(temporary)
            candidates = root / "candidates"
            candidates.mkdir()
            outside = root / "outside.rs"
            outside.write_text("pub fn ignored_term() {}\n", encoding="utf-8")
            descriptor = {
                "group_id": "bounded-node", "status": "rejected",
                "source_path": str(outside), "sha256": _sha(outside.read_bytes()),
                "public_symbols": [], "required_symbols": [], "unsafe_count": 0,
            }

            result = integration.integrate_candidates(
                {"dag": {"bounded-node": []}}, [descriptor], candidates, root / "project",
            )

            self.assertEqual("failed", result["status"])
            self.assertEqual("candidate_path_untrusted", result["diagnostics"][0]["code"])
            self.assertFalse((root / "project").exists())

    def test_symbol_dependency_dag_and_unsafe_failures_are_structured(self) -> None:
        with tempfile.TemporaryDirectory(prefix="migration-gates-") as temporary:
            root = Path(temporary)
            candidates = root / "candidates"
            candidates.mkdir()
            one = _descriptor(
                candidates, "group-one", "one.rs", b"pub fn shared_term() {}\n",
                public_symbols=["shared_term"],
            )
            two = _descriptor(
                candidates, "group-two", "two.rs", b"pub fn other_term() {}\n",
                public_symbols=["shared_term"], unsafe_count=1,
            )
            cases = [
                (
                    {"dag": {"group-one": [], "group-two": []}}, [one, two],
                    "symbol_provider_conflict",
                ),
                (
                    {"dag": {"group-one": []}},
                    [dict(one, required_symbols=["absent_term"])], "required_symbol_missing",
                ),
                (
                    {"dag": {"group-one": ["group-two"], "group-two": ["group-one"]}},
                    [one, dict(two, public_symbols=["other_term"])], "dag_cycle",
                ),
                (
                    {"dag": {"group-two": []}, "unsafe_policy": {"allow_unsafe": False}},
                    [dict(two, public_symbols=["other_term"])], "unsafe_policy_exceeded",
                ),
            ]
            for index, (manifest, descriptors, code) in enumerate(cases):
                with self.subTest(code=code):
                    result = integration.integrate_candidates(
                        manifest, descriptors, candidates, root / f"project-{index}",
                    )
                    self.assertEqual("failed", result["status"])
                    self.assertEqual(code, result["diagnostics"][0]["code"])
                    self.assertFalse(result["cargo_executed"])


if __name__ == "__main__":
    unittest.main()
