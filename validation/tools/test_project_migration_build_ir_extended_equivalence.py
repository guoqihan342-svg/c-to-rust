from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.build_ir import (
    finalize_build_ir,
    semantic_projection,
)
from validation.tools._project_migration_harness.build_ir_validation import (
    BuildIRValidationError,
    validate_build_ir,
)
from validation.tools.project_migration_build_ir_extended_test_support import (
    load_extended_manifest,
    materialize_extended_lane,
)


class ProjectMigrationBuildIRExtendedEquivalenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="build-ir-extended-equivalence-",
        )
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def lanes(self, prefix: str = "same"):
        return [
            materialize_extended_lane(self.base, f"{prefix}-{lane}", lane)
            for lane in ("cmake", "ninja", "meson")
        ]

    def test_cmake_ninja_and_meson_share_one_canonical_projection(self) -> None:
        lanes = self.lanes()
        projections = [semantic_projection(lane.build_ir) for lane in lanes]

        for lane in lanes:
            validate_build_ir(lane.build_ir)
            self.assertEqual("verified", lane.verification["status"])
        self.assertEqual(projections[0], projections[1])
        self.assertEqual(projections[0], projections[2])
        self.assertEqual(
            1,
            len({lane.build_ir["semantic_sha256"] for lane in lanes}),
        )

        expected = load_extended_manifest(lanes[0].project_root)["expected"]
        self._assert_extended_topology(lanes[0].build_ir, expected)
        self.assertNotEqual(
            lanes[0].build_ir["raw_fact_refs"],
            lanes[1].build_ir["raw_fact_refs"],
        )

    def test_meson_private_shapes_are_retained_only_as_provenance(self) -> None:
        lane = materialize_extended_lane(self.base, "meson-private", "meson")
        full = json.dumps(lane.build_ir, sort_keys=True)
        projected = json.dumps(semantic_projection(lane.build_ir), sort_keys=True)

        self.assertIn("meson_target_id", full)
        self.assertIn("meson_source_groups", full)
        for private in (
            "meson_target_id", "meson_target_type", "meson_source_groups",
            "compiler_summary", "parameters_summary",
        ):
            self.assertNotIn(private, projected)

    def test_declared_external_dependency_changes_only_declared_semantics(self) -> None:
        baseline = materialize_extended_lane(self.base, "meson-base", "meson")
        declared = materialize_extended_lane(
            self.base, "meson-declared", "meson", declared_dependency=True,
        )

        self.assertNotEqual(
            baseline.build_ir["semantic_sha256"],
            declared.build_ir["semantic_sha256"],
        )
        baseline_names = {
            item["name"] for item in baseline.build_ir["external_dependencies"]
        }
        declared_names = {
            item["name"] for item in declared.build_ir["external_dependencies"]
        }
        self.assertEqual({"-pthread"}, baseline_names)
        self.assertEqual({"-pthread", "threads"}, declared_names)
        self.assertEqual(
            baseline.build_ir["target_closure"],
            declared.build_ir["target_closure"],
        )

    def test_repository_rename_does_not_change_meson_semantics(self) -> None:
        first = materialize_extended_lane(self.base, "rename-first", "meson")
        second = materialize_extended_lane(self.base, "rename-second", "meson")

        self.assertEqual(
            first.build_ir["semantic_sha256"],
            second.build_ir["semantic_sha256"],
        )
        self.assertNotEqual(
            first.build_ir["raw_fact_refs"], second.build_ir["raw_fact_refs"],
        )

    def test_compile_facts_drive_canonical_toolchain_semantics(self) -> None:
        clang = self.lanes("toolchain-clang")
        gcc = [
            materialize_extended_lane(
                self.base, f"toolchain-gcc-{lane}", lane, compiler="gcc",
            )
            for lane in ("cmake", "ninja", "meson")
        ]

        self.assertEqual(1, len({item.build_ir["semantic_sha256"] for item in clang}))
        self.assertEqual(1, len({item.build_ir["semantic_sha256"] for item in gcc}))
        self.assertNotEqual(
            clang[0].build_ir["semantic_sha256"],
            gcc[0].build_ir["semantic_sha256"],
        )
        for lane in gcc:
            self.assertEqual({"gcc"}, {
                item["driver"] for item in lane.build_ir["toolchains"]
            })
            self.assertEqual({"gcc"}, {
                item["compiler"] for item in lane.build_ir["translation_units"]
            })

    def test_meson_reported_compiler_is_audit_only(self) -> None:
        baseline = materialize_extended_lane(
            self.base, "reported-baseline", "meson",
        )
        reported = materialize_extended_lane(
            self.base, "reported-drift", "meson", reported_compiler="gcc",
        )

        self.assertEqual(
            baseline.build_ir["semantic_sha256"],
            reported.build_ir["semantic_sha256"],
        )
        self.assertNotEqual(
            baseline.build_ir["raw_fact_refs"], reported.build_ir["raw_fact_refs"],
        )
        self.assertEqual({"clang"}, {
            item["driver"] for item in reported.build_ir["toolchains"]
        })

    def test_v1_and_invalid_archive_semantics_fail_closed(self) -> None:
        lane = materialize_extended_lane(self.base, "schema-negative", "cmake")
        legacy = copy.deepcopy(lane.build_ir)
        legacy["schema_version"] = 1
        legacy["extractor"]["version"] = "1"
        legacy = finalize_build_ir(legacy)
        with self.assertRaisesRegex(
            BuildIRValidationError, "build_ir_schema_version_invalid",
        ):
            validate_build_ir(legacy)

        for mutation in ("missing", "negative-ranlib"):
            with self.subTest(mutation=mutation):
                altered = copy.deepcopy(lane.build_ir)
                archive = next(
                    item for item in altered["targets"]
                    if item["kind"] == "archive"
                )
                if mutation == "missing":
                    del archive["archive_semantics"]
                else:
                    archive["archive_semantics"]["ranlib_passes"] = -1
                altered = finalize_build_ir(altered)
                with self.assertRaisesRegex(
                    BuildIRValidationError, "build_ir_archive_semantics_invalid",
                ):
                    validate_build_ir(altered)

    def _assert_extended_topology(self, build_ir, expected) -> None:
        self.assertEqual(
            expected["sources"],
            [item["source"]["path"] for item in build_ir["translation_units"]],
        )
        targets = {item["outputs"][0]["path"]: item for item in build_ir["targets"]}
        archive = targets[expected["archive"]]
        linked = targets[expected["link"]]
        self.assertEqual("archive", archive["kind"])
        self.assertEqual(
            {"operation": "qc", "ranlib_passes": 1},
            archive["archive_semantics"],
        )
        self.assertEqual(
            expected["archive_inputs"],
            [item["binding"]["path"] for item in archive["ordered_inputs"]],
        )
        self.assertEqual(
            expected["link_inputs"],
            [item["binding"]["path"] for item in linked["ordered_inputs"]],
        )
        self.assertEqual(
            expected["external_link_arguments"], linked["ordered_link_arguments"],
        )
        self.assertEqual({"clang"}, {
            item["driver"] for item in build_ir["toolchains"]
        })


if __name__ == "__main__":
    unittest.main()
