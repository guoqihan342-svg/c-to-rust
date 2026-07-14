from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import write_json_artifact
from validation.tools._project_migration_harness.build_ir import finalize_build_ir
from validation.tools._project_migration_harness.build_ir_projection import (
    project_build_ir,
)
from validation.tools._project_migration_harness.build_ir_validation import (
    BuildIRValidationError, validate_build_ir,
)
from validation.tools._project_migration_harness.discovery import discover_project
from validation.tools._project_migration_harness.generated_closure import (
    verify_generated_build_closure,
)


class ExternalNativeLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="external-native-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def _write(self, root: Path, relative: str, value: str | bytes) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else value.encode("utf-8"))
        return path

    def _project(
        self, name: str, external: str,
    ) -> tuple[Path, dict, dict, dict]:
        root = self.base / name
        root.mkdir()
        source = self._write(root, "src/unit.c", "int unit(void) { return 1; }\n")
        self._write(root, "build/unit.o", b"object")
        self._write(root, "build/program", b"program")
        self._write(
            root, "build/CMakeFiles/sample.dir/link.txt",
            f"clang unit.o {external} -o program\n",
        )
        database = self._write(root, "build/compile_commands.json", json.dumps([{
            "directory": str(root / "build"),
            "file": str(source),
            "arguments": [
                "clang", "-c", str(source), "-o", "unit.o",
            ],
            "output": "unit.o",
        }]))
        closure, verification, build_ir = self._build_ir(root, database, name)
        return root, closure, verification, build_ir

    def _build_ir(
        self, root: Path, database: Path, output_name: str,
    ) -> tuple[dict, dict, dict]:
        discovery = discover_project(root, compile_database=database)
        closure = discovery["generated_build_closure"]
        verification = verify_generated_build_closure(root, closure)
        output = self.base / f"{output_name}-out"
        output.mkdir()
        refs = [
            {"role": role, **write_json_artifact(output, relative, payload)}
            for role, relative, payload in (
                ("discovery", "plan/discovery.json", discovery),
                ("generated-build-closure", "plan/closure.json", closure),
                ("generated-build-closure-verification", "plan/verify.json", verification),
            )
        ]
        build_ir = project_build_ir(discovery, closure, verification, refs)
        return closure, verification, build_ir

    def test_absolute_native_library_is_sanitized_and_keeps_boundary(self) -> None:
        external = "/vendor/private/location/libalpha.so.3"

        _root, closure, verification, build_ir = self._project(
            "sanitized", external,
        )

        self.assertEqual("ready", closure["status"], closure)
        self.assertEqual("verified", verification["status"], verification)
        target = closure["target_link_closure"]["targets"][0]
        self.assertEqual([{
            "argument_index": 1,
            "format": "shared-library",
            "name": "libalpha.so.3",
            "resolution": "unresolved-host-native-link",
            "resolved": False,
            "source_argument_sha256": target["external_native_libraries"][0][
                "source_argument_sha256"
            ],
        }], target["external_native_libraries"])
        self.assertNotIn(external, json.dumps(closure))
        validate_build_ir(build_ir)
        dependency = next(
            item for item in build_ir["external_dependencies"]
            if item["kind"] == "unresolved-native-library"
        )
        self.assertEqual("libalpha.so.3", dependency["name"])
        self.assertFalse(dependency["resolved"])
        self.assertEqual("ready_with_boundaries", build_ir["status"])
        self.assertFalse(build_ir["claim_boundary"]["native_link_config_resolved"])
        self.assertEqual(1, build_ir["claim_boundary"][
            "unresolved_native_dependency_count"
        ])
        self.assertIn("native_link_config_unresolved", {
            item["kind"] for item in build_ir["boundaries"]
        })

    def test_host_directory_drift_does_not_change_build_semantics(self) -> None:
        root, _closure, _verification, first = self._project(
            "drift", "/one/host/root/libalpha.so.3",
        )
        self._write(
            root, "build/CMakeFiles/sample.dir/link.txt",
            "clang unit.o /different/host/root/libalpha.so.3 -o program\n",
        )
        _closure, _verification, second = self._build_ir(
            root, root / "build/compile_commands.json", "drift-second",
        )

        self.assertEqual(first["semantic_sha256"], second["semantic_sha256"])
        first_dependency = next(
            item for item in first["external_dependencies"]
            if item["kind"] == "unresolved-native-library"
        )
        second_dependency = next(
            item for item in second["external_dependencies"]
            if item["kind"] == "unresolved-native-library"
        )
        self.assertNotEqual(
            first_dependency["provenance"]["source_argument_sha256"],
            second_dependency["provenance"]["source_argument_sha256"],
        )

    def test_tampered_external_library_projection_fails_reopen(self) -> None:
        root, closure, _verification, _build_ir = self._project(
            "tamper", "/system/lib/libalpha.so",
        )
        altered = copy.deepcopy(closure)
        altered["target_link_closure"]["targets"][0][
            "external_native_libraries"
        ][0]["name"] = "libbeta.so"

        verification = verify_generated_build_closure(root, altered)

        self.assertEqual("blocked", verification["status"])
        self.assertIn("target_link_closure_drift", {
            item["kind"] for item in verification["blockers"]
        })

    def test_unknown_external_path_and_absolute_object_stay_blocked(self) -> None:
        for index, external in enumerate((
            "/outside/object/unit.o", "/outside/data/not-a-library.txt",
        )):
            with self.subTest(external=external):
                root = self.base / f"blocked-{index}"
                root.mkdir()
                source = self._write(root, "src/unit.c", "int unit(void) { return 1; }\n")
                self._write(root, "build/unit.o", b"object")
                self._write(root, "build/program", b"program")
                self._write(
                    root, "build/CMakeFiles/sample.dir/link.txt",
                    f"clang unit.o {external} -o program\n",
                )
                database = self._write(
                    root, "build/compile_commands.json", json.dumps([{
                        "directory": str(root / "build"), "file": str(source),
                        "arguments": ["clang", "-c", str(source), "-o", "unit.o"],
                        "output": "unit.o",
                    }]),
                )

                closure = discover_project(
                    root, compile_database=database,
                )["generated_build_closure"]

                self.assertEqual("blocked", closure["status"])
                blocker_kinds = {
                    item["kind"] for item in closure["blockers"]
                }
                self.assertTrue(blocker_kinds & {
                    "link_input_foreign_absolute_path",
                    "link_input_path_outside_repository",
                })
                self.assertNotIn(external, json.dumps(closure))

    def test_native_dependency_identity_tamper_is_rejected(self) -> None:
        _root, _closure, _verification, build_ir = self._project(
            "identity", "/system/lib/libalpha.so",
        )
        altered = copy.deepcopy(build_ir)
        dependency = next(
            item for item in altered["external_dependencies"]
            if item["kind"] == "unresolved-native-library"
        )
        dependency["dependency_id"] = "external-" + "0" * 24

        with self.assertRaisesRegex(
            BuildIRValidationError, "build_ir_native_dependency_identity_invalid",
        ):
            validate_build_ir(altered)

    def test_native_dependency_claim_and_boundary_are_recomputed(self) -> None:
        _root, _closure, _verification, build_ir = self._project(
            "summary", "/system/lib/libalpha.so",
        )
        mutations = (
            ("claim", "build_ir_native_claim_boundary_invalid"),
            ("boundary", "build_ir_native_boundary_mismatch"),
            ("kind", "build_ir_external_dependency_kind_invalid"),
        )
        for mutation, reason in mutations:
            with self.subTest(mutation=mutation):
                altered = copy.deepcopy(build_ir)
                dependency = next(
                    item for item in altered["external_dependencies"]
                    if item["kind"] == "unresolved-native-library"
                )
                if mutation == "claim":
                    altered["claim_boundary"]["native_link_config_resolved"] = True
                    altered["claim_boundary"]["unresolved_native_dependency_count"] = 0
                elif mutation == "boundary":
                    altered["boundaries"] = [
                        item for item in altered["boundaries"]
                        if item["kind"] != "native_link_config_unresolved"
                    ]
                else:
                    dependency["kind"] = "unknown-external-dependency"
                altered = finalize_build_ir(altered)
                with self.assertRaisesRegex(BuildIRValidationError, reason):
                    validate_build_ir(altered)


if __name__ == "__main__":
    unittest.main()
