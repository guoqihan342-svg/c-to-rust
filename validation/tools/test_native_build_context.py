from __future__ import annotations

import json
import tempfile
import unittest
from collections.abc import Iterator, Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from validation.tools.native_build_closure import sha256_path
from validation.tools.native_build_context import resolve_native_build_context


class NativeBuildContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="native-build-context-")
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.source_root = self.root / "vendor" / "source"
        self.source_include = self.source_root / "include"
        self.generated_include = self.root / "closure" / "include"
        self.source_include.mkdir(parents=True)
        self.generated_include.mkdir(parents=True)
        (self.source_root / "unit.c").write_text("int unit(void) { return 1; }\n")
        (self.source_include / "api.h").write_text("int unit(void);\n")
        (self.generated_include / "config.h").write_text("#define FEATURE 1\n")
        self.compile_database = self.root / "closure" / "compile_commands.json"
        self.compile_database.write_text("[]\n")
        self.artifact = self.root / "closure" / "libnative.a"
        self.artifact.write_bytes(b"native archive")
        self.manifest_path = self.root / "closure" / "closure.json"

    def test_projects_only_authoritative_verified_translator_context(self) -> None:
        spec = _PoisonSpec(self._write_spec())

        context = resolve_native_build_context(spec, self.root)

        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context["defines"], ["FEATURE=1", "NATIVE_BUILD"])
        self.assertEqual(
            context["include_paths"],
            ["vendor/source/include", "closure/include"],
        )
        self.assertEqual(
            context["compile_database"], self._ref(self.compile_database)
        )
        self.assertEqual(context["source_root"], self._ref(self.source_root))
        self.assertEqual(context["target_abi"]["pointer_width"], 64)
        self.assertEqual(context["toolchain"], {"cc": "GNU 13.3.0"})
        self.assertEqual(context["build_config"]["build_target"], "native")
        self.assertEqual(
            context["symbol_bindings"],
            [
                {
                    "source_symbol": "public_name",
                    "linked_symbol": "exported_name",
                    "artifact": self._ref(self.artifact),
                }
            ],
        )
        serialized = json.dumps(context, sort_keys=True)
        self.assertNotIn("LEGACY_VALUE_MUST_NOT_APPEAR", serialized)
        self.assertNotIn("legacy/include/must-not-appear", serialized)

    def test_absent_closure_returns_none(self) -> None:
        self.assertIsNone(resolve_native_build_context({}, self.root))
        self.assertIsNone(
            resolve_native_build_context(
                {"build_profile": {"defines": ["LEGACY"]}}, self.root
            )
        )

    def test_invalid_declared_closure_raises_instead_of_falling_back(self) -> None:
        with self.assertRaisesRegex(ValueError, "closure_manifest"):
            resolve_native_build_context(
                {
                    "build_profile": {
                        "oracle_build": {
                            "schema_version": 1,
                            "mode": "linked_artifacts_v1",
                        }
                    }
                },
                self.root,
            )

    def test_hash_drift_blocks_projection(self) -> None:
        spec = self._write_spec()
        self.compile_database.write_text('[{"drifted": true}]\n')

        with self.assertRaisesRegex(ValueError, "sha256 does not match"):
            resolve_native_build_context(spec, self.root)

    def test_projection_paths_are_canonical_repo_relative(self) -> None:
        context = resolve_native_build_context(self._write_spec(), self.root)
        assert context is not None

        for path in _collect_ref_paths(context):
            self.assertFalse(PurePosixPath(path).is_absolute(), path)
            self.assertFalse(PureWindowsPath(path).is_absolute(), path)
            self.assertFalse(PureWindowsPath(path).drive, path)
            self.assertNotIn("..", PurePosixPath(path).parts)
            self.assertNotIn("\\", path)
            self.assertEqual(PurePosixPath(path).as_posix(), path)

    def test_command_working_directory_and_output_fields_do_not_leak(self) -> None:
        context = resolve_native_build_context(self._write_spec(), self.root)
        assert context is not None
        serialized = json.dumps(context, sort_keys=True)

        keys = _collect_keys(context)
        for forbidden in (
            "argv",
            "arguments",
            "command",
            "working_directory",
            "output",
            "output_path",
        ):
            self.assertNotIn(forbidden, keys)
        self.assertNotIn(".native-build-context-probe", serialized)
        self.assertNotIn(str(self.root), serialized)

    def test_host_absolute_toolchain_value_is_rejected(self) -> None:
        for value in ("/usr/bin/cc", "C:\\tool\\cc.exe", "\\\\server\\share\\cc.exe"):
            with self.subTest(value=value):
                spec = self._write_spec(toolchain={"cc": value})
                with self.assertRaisesRegex(ValueError, "host-absolute path"):
                    resolve_native_build_context(spec, self.root)

    def _write_spec(self, *, toolchain: dict[str, str] | None = None) -> dict[str, Any]:
        manifest = {
            "schema_version": 1,
            "build_config": {
                "generator": "Ninja",
                "build_type": "Release",
                "build_target": "native",
                "configure_defines": ["FEATURE=1"],
            },
            "target_abi": {
                "triple": "x86_64-unknown-linux-gnu",
                "endianness": "little",
                "pointer_width": 64,
            },
            "toolchain": toolchain or {"cc": "GNU 13.3.0"},
            "source_root": self._ref(self.source_root),
            "compile_database": self._ref(self.compile_database),
            "defines": ["FEATURE=1", "NATIVE_BUILD"],
            "source_include_dirs": [self._ref(self.source_include)],
            "generated_include_dirs": [self._ref(self.generated_include)],
            "link_artifacts": [self._ref(self.artifact)],
            "system_link_args": ["-pthread"],
            "symbol_bindings": [
                {
                    "source_symbol": "public_name",
                    "linked_symbol": "exported_name",
                    "artifact": self._ref(self.artifact),
                }
            ],
        }
        self.manifest_path.write_text(json.dumps(manifest, sort_keys=True))
        return {
            "target": "must-not-be-read",
            "target_id": "must-not-be-read",
            "project": "must-not-be-read",
            "function": "must-not-be-read",
            "function_name": "must-not-be-read",
            "slice": "must-not-be-read",
            "slice_id": "must-not-be-read",
            "name": "must-not-be-read",
            "build_profile": {
                "defines": ["LEGACY_VALUE_MUST_NOT_APPEAR"],
                "include_paths": ["legacy/include/must-not-appear"],
                "oracle_build": {
                    "schema_version": 1,
                    "mode": "linked_artifacts_v1",
                    "closure_manifest": self._ref(self.manifest_path),
                },
            },
        }

    def _ref(self, path: Path) -> dict[str, str]:
        return {
            "path": path.relative_to(self.root).as_posix(),
            "sha256": sha256_path(path),
        }


class _PoisonSpec(Mapping[str, Any]):
    FORBIDDEN = {
        "target",
        "target_id",
        "project",
        "function",
        "function_name",
        "slice",
        "slice_id",
        "name",
    }

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


def _collect_ref_paths(value: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        if set(value) == {"path", "sha256"}:
            paths.append(str(value["path"]))
        for item in value.values():
            paths.extend(_collect_ref_paths(item))
    elif isinstance(value, list):
        for item in value:
            paths.extend(_collect_ref_paths(item))
    return paths


def _collect_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        keys.update(str(key) for key in value)
        for item in value.values():
            keys.update(_collect_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_collect_keys(item))
    return keys


if __name__ == "__main__":
    unittest.main()
