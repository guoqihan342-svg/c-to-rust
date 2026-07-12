from __future__ import annotations

import json
import tempfile
import unittest
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any
from unittest.mock import patch

import jsonschema

from validation.tools import native_build_closure
from validation.tools import native_build_closure_paths
from validation.tools.native_build_closure import (
    resolve_native_build_closure,
    resolve_native_build_closure_or_block,
    sha256_path,
)


class NativeBuildClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="native-build-closure-")
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.evidence_dir = self.root / "evidence"
        self.evidence_dir.mkdir()
        self.harness = self.evidence_dir / "oracle.c"
        self.harness.write_text("int main(void) { return 0; }\n", encoding="utf-8")
        self.source_root = self.root / "vendor" / "source"
        self.source_root.mkdir(parents=True)
        (self.source_root / "unit.c").write_text("int unit(void) { return 1; }\n", encoding="utf-8")
        self.include_dir = self.root / "build" / "generated"
        self.include_dir.mkdir(parents=True)
        (self.include_dir / "config.h").write_text("#define GENERATED 1\n", encoding="utf-8")
        self.first_artifact = self.root / "build" / "first.a"
        self.second_artifact = self.root / "build" / "second.a"
        self.first_artifact.write_bytes(b"first archive")
        self.second_artifact.write_bytes(b"second archive")
        self.compile_database = self.root / "build" / "compile_commands.json"
        self.compile_database.write_text("[]\n", encoding="utf-8")

    def test_success_uses_manifest_defines_includes_and_ordered_link_args(self) -> None:
        spec = self._write_closure()

        contract = resolve_native_build_closure(spec, self.root, self.evidence_dir, self.harness)

        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(contract["defines"], ["FEATURE=7", "NATIVE_BUILD"])
        self.assertEqual(contract["resolved_include_paths"], ["build/generated"])
        self.assertEqual(
            contract["compile_database"]["path"],
            "build/compile_commands.json",
        )
        self.assertEqual(contract["ordered_artifact_args"], ["build/first.a", "build/second.a"])
        self.assertEqual(
            contract["argv"],
            [
                "cc",
                "-std=c99",
                "-DFEATURE=7",
                "-DNATIVE_BUILD",
                "-Ibuild/generated",
                "oracle.c",
                "build/first.a",
                "build/second.a",
                "-pthread",
                "-lm",
                "-o",
                "oracle.exe",
            ],
        )

    def test_harness_output_may_be_created_after_contract_resolution(self) -> None:
        spec = self._write_closure()
        self.harness.unlink()

        contract = resolve_native_build_closure(
            spec,
            self.root,
            self.evidence_dir,
            self.harness,
        )

        self.assertEqual(contract["argv"][5], "oracle.c")

    def test_directory_hash_excludes_nested_git_metadata(self) -> None:
        baseline = sha256_path(self.source_root)
        metadata = self.source_root / ".git"
        metadata.mkdir()
        (metadata / "config").write_text("machine-specific\n", encoding="utf-8")

        self.assertEqual(sha256_path(self.source_root), baseline)

    def test_evidence_directory_may_be_outside_repository(self) -> None:
        spec = self._write_closure()
        with tempfile.TemporaryDirectory(prefix="native-build-external-evidence-") as tmp:
            evidence = Path(tmp)
            harness = evidence / "oracle.c"

            contract = resolve_native_build_closure(spec, self.root, evidence, harness)

            self.assertEqual(contract["working_directory"], evidence.resolve().as_posix())
            self.assertIn("oracle.c", contract["argv"])

    def test_missing_oracle_build_returns_none_but_missing_closure_fails(self) -> None:
        self.assertIsNone(
            resolve_native_build_closure(
                {"build_profile": {"defines": ["LEGACY"]}},
                self.root,
                self.evidence_dir,
                self.harness,
            )
        )
        with self.assertRaisesRegex(ValueError, "closure_manifest"):
            resolve_native_build_closure(
                {
                    "build_profile": {
                        "oracle_build": {"schema_version": 1, "mode": "linked_artifacts_v1"}
                    }
                },
                self.root,
                self.evidence_dir,
                self.harness,
            )

        bound_spec = self._write_closure()
        self.second_artifact.unlink()
        with self.assertRaisesRegex(ValueError, "does not exist"):
            resolve_native_build_closure(
                bound_spec, self.root, self.evidence_dir, self.harness
            )

    def test_parent_path_escape_is_rejected(self) -> None:
        spec = self._write_closure()
        spec["build_profile"]["oracle_build"]["closure_manifest"]["path"] = "../closure.json"

        with self.assertRaisesRegex(ValueError, "must not be absolute or contain"):
            resolve_native_build_closure(spec, self.root, self.evidence_dir, self.harness)

    def test_symlinked_artifact_is_rejected(self) -> None:
        spec = self._write_closure()
        real_is_link = native_build_closure_paths._is_link
        linked_target = self.first_artifact.resolve()

        def classify(path: Path) -> bool:
            return path.resolve() == linked_target or real_is_link(path)

        with patch.object(native_build_closure_paths, "_is_link", side_effect=classify):
            with self.assertRaisesRegex(ValueError, "symlink"):
                resolve_native_build_closure(spec, self.root, self.evidence_dir, self.harness)

    def test_hash_drift_is_rejected(self) -> None:
        spec = self._write_closure()
        self.first_artifact.write_bytes(b"drifted archive")

        with self.assertRaisesRegex(ValueError, "sha256 does not match"):
            resolve_native_build_closure(spec, self.root, self.evidence_dir, self.harness)

        blocked = resolve_native_build_closure_or_block(
            spec,
            self.root,
            self.evidence_dir,
            self.harness,
        )
        self.assertEqual(blocked["status"], "native_build_closure_invalid")
        self.assertEqual(blocked["argv"], [])
        self.assertEqual(blocked["link_strategy"], "native_build_closure_invalid")

    def test_project_and_function_names_cannot_select_logic(self) -> None:
        ordinary = self._write_closure()
        poison = _PoisonSpec(ordinary)

        contract = resolve_native_build_closure(poison, self.root, self.evidence_dir, self.harness)

        self.assertEqual(contract["mode"], "linked_artifacts_v1")
        self.assertEqual(contract["ordered_artifact_args"], ["build/first.a", "build/second.a"])

    def test_repository_closure_manifests_match_schema(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        schema = json.loads(
            (
                repo_root
                / "validation/native-build-closure-template/native-build-closure.schema.json"
            ).read_text(encoding="utf-8")
        )
        validator = jsonschema.Draft7Validator(schema)
        manifests = sorted(
            (repo_root / "validation/native-build-closures").glob("*/closure.json")
        )

        self.assertGreaterEqual(len(manifests), 2)
        for manifest in manifests:
            with self.subTest(manifest=manifest):
                validator.validate(json.loads(manifest.read_text(encoding="utf-8")))

    def _write_closure(
        self,
        *,
        artifact_paths: list[Path] | None = None,
        symbols: list[tuple[str, Path]] | None = None,
    ) -> dict[str, Any]:
        artifacts = artifact_paths or [self.first_artifact, self.second_artifact]
        symbol_rows = symbols or [
            ("first_symbol", self.first_artifact),
            ("second_symbol", self.second_artifact),
        ]
        manifest = {
            "schema_version": 1,
            "build_config": {
                "generator": "Ninja",
                "build_type": "Release",
                "build_target": "native",
                "configure_defines": ["FEATURE=7"],
            },
            "target_abi": {
                "triple": "x86_64-unknown-linux-gnu",
                "endianness": "little",
                "pointer_width": 64,
            },
            "toolchain": {
                "cc": "GNU 13.3.0",
                "cmake": "3.28.3",
            },
            "source_root": self._ref(self.source_root),
            "compile_database": self._ref(self.compile_database),
            "defines": ["FEATURE=7", "NATIVE_BUILD"],
            "source_include_dirs": [],
            "generated_include_dirs": [self._ref(self.include_dir)],
            "link_artifacts": [self._ref(path) for path in artifacts],
            "system_link_args": ["-pthread", "-lm"],
            "symbol_bindings": [
                {
                    "source_symbol": symbol,
                    "linked_symbol": symbol,
                    "artifact": self._ref(path),
                }
                for symbol, path in symbol_rows
            ],
        }
        manifest_path = self.root / "build" / "closure.json"
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        return {
            "target_id": "must-not-be-read",
            "project": "must-not-be-read",
            "function_name": "must-not-be-read",
            "slice_id": "must-not-be-read",
            "name": "must-not-be-read",
            "build_profile": {
                "defines": ["LEGACY_VALUE_MUST_NOT_APPEAR"],
                "include_paths": ["legacy/include/must-not-appear"],
                "oracle_build": {
                    "schema_version": 1,
                    "mode": "linked_artifacts_v1",
                    "closure_manifest": self._ref(manifest_path),
                },
            },
        }

    def _ref(self, path: Path) -> dict[str, str]:
        return {
            "path": path.relative_to(self.root).as_posix(),
            "sha256": sha256_path(path),
        }


class _PoisonSpec(Mapping[str, Any]):
    FORBIDDEN = {"target_id", "project", "function", "function_name", "slice", "slice_id", "name"}

    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def __getitem__(self, key: str) -> Any:
        if key in self.FORBIDDEN:
            raise AssertionError(f"resolver read forbidden identity field: {key}")
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self.FORBIDDEN:
            raise AssertionError(f"resolver read forbidden identity field: {key}")
        return self._values.get(key, default)


if __name__ == "__main__":
    unittest.main()
