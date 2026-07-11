from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from validation.tools._validate_ai_exact_evidence_parts.io import EvidenceError, EvidenceStore


class AiExactEvidencePathContractTests(unittest.TestCase):
    def test_root_relative_and_parent_relative_paths_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "evidence"
            attempt = root / "attempt"
            nested = attempt / "gates"
            nested.mkdir(parents=True)
            root_artifact = root / "summary.json"
            gate = attempt / "gate.json"
            nested_gate = nested / "gate.json"
            for path in (root_artifact, gate, nested_gate):
                path.write_text("{}\n", encoding="utf-8")
            store = EvidenceStore(root)

            self.assertEqual(store.resolve("summary.json", "summary"), root_artifact.resolve())
            self.assertEqual(store.resolve("gate.json", "gate", parent=attempt), gate.resolve())
            self.assertEqual(
                store.resolve("gates/gate.json", "nested_gate", parent=attempt),
                nested_gate.resolve(),
            )

    def test_parent_component_escape_is_rejected_before_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "evidence"
            root.mkdir()
            store = EvidenceStore(root)

            with self.assertRaises(EvidenceError) as raised:
                store.resolve("../outside.json", "artifact")

            self.assertEqual(raised.exception.code, "path_escape")

    def test_absolute_drive_and_backslash_paths_are_rejected(self) -> None:
        invalid_paths = (
            "/absolute.json",
            "C:/absolute.json",
            "C:drive-relative.json",
            "gates\\gate.json",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "evidence"
            root.mkdir()
            store = EvidenceStore(root)

            for value in invalid_paths:
                with self.subTest(value=value), self.assertRaises(EvidenceError) as raised:
                    store.resolve(value, "artifact")
                self.assertEqual(raised.exception.code, "invalid_path")

    def test_empty_dot_and_nul_components_are_rejected(self) -> None:
        invalid_paths = (
            "",
            ".",
            "./gate.json",
            "gates/./gate.json",
            "gates//gate.json",
            "gates/",
            "gate\x00.json",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "evidence"
            root.mkdir()
            store = EvidenceStore(root)

            for value in invalid_paths:
                with self.subTest(value=value), self.assertRaises(EvidenceError) as raised:
                    store.resolve(value, "artifact")
                self.assertEqual(raised.exception.code, "invalid_path")

    def test_nested_parent_component_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "evidence"
            root.mkdir()
            store = EvidenceStore(root)

            with self.assertRaises(EvidenceError) as raised:
                store.resolve("gates/../summary.json", "artifact")

            self.assertEqual(raised.exception.code, "path_escape")


if __name__ == "__main__":
    unittest.main()
