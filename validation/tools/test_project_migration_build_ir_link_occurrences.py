from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.build_ir_link_occurrences import (
    project_link_occurrences, validate_link_occurrence_authority,
)
from validation.tools._project_migration_harness.build_ir_link_search_roots import (
    project_link_search_roots,
)
from validation.tools._project_migration_harness.build_ir_external_dependencies import (
    NATIVE_DEPENDENCY_KIND, ORDERED_LINK_ARGUMENT_KIND,
)


SHA = "a" * 64


class BuildIRLinkOccurrenceTests(unittest.TestCase):
    def setUp(self) -> None:
        first = _file("obj/first.o")
        second = _file("obj/second.o")
        self.inputs = [
            {"ordinal": 0, "role": "link-input", "binding": first,
             "dependency_target_id": "object-first"},
            {"ordinal": 1, "role": "link-input", "binding": second,
             "dependency_target_id": "object-second"},
        ]
        self.external = [
            {
                "dependency_id": "system-m", "kind": ORDERED_LINK_ARGUMENT_KIND,
                "name": "-lm", "consumer_target_ids": ["target-bin"],
            },
            {
                "dependency_id": "native-x", "kind": NATIVE_DEPENDENCY_KIND,
                "name": "libx.so", "consumer_target_ids": ["target-bin"],
                "ordinal": 4,
            },
        ]
        self.raw = {
            "inputs": [first, second],
            "search_roots": [_directory("vendor/lib")],
            "ordered_system_link_args": ["-lm"],
            "external_native_libraries": [{"name": "libx.so"}],
            "ordered_link_occurrences": [
                _raw(0, 0, 1, "input", 0),
                _raw(1, 1, 1, "system-argument", 0),
                _raw(2, 2, 2, "search-root", 0),
                _raw(3, 4, 1, "external-native-library", 0),
                _raw(4, 5, 1, "input", 1),
            ],
        }

    def test_projects_and_validates_cross_category_order(self) -> None:
        projected = project_link_occurrences(
            self.raw, "target-bin", self.inputs, self.external,
        )
        self.assertIsNotNone(projected)
        self.assertEqual(
            ["input", "system-argument", "search-root",
             "external-native-library", "input"],
            [item["kind"] for item in projected],
        )
        self.assertEqual([0, 1], [
            item["input_ordinal"] for item in projected
            if item["kind"] == "input"
        ])
        validate_link_occurrence_authority(
            [{"target_id": "target-bin", "kind": "link",
              "ordered_inputs": self.inputs, "ordered_link_arguments": ["-lm"],
              "ordered_link_occurrences": projected,
              "ordered_link_search_roots": project_link_search_roots(self.raw)}],
            self.external,
        )

    def test_partition_or_projected_order_drift_fails_closed(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["ordered_link_occurrences"].pop()
        with self.assertRaisesRegex(ValueError, "partition"):
            project_link_occurrences(
                raw, "target-bin", self.inputs, self.external,
            )

        projected = project_link_occurrences(
            self.raw, "target-bin", self.inputs, self.external,
        )
        projected[2]["argument_index"] = 1
        with self.assertRaisesRegex(ValueError, "argument_order"):
            validate_link_occurrence_authority(
                [{"target_id": "target-bin", "kind": "link",
                  "ordered_inputs": self.inputs,
                  "ordered_link_arguments": ["-lm"],
                  "ordered_link_occurrences": projected,
                  "ordered_link_search_roots": project_link_search_roots(self.raw)}],
                self.external,
            )

        projected = project_link_occurrences(
            self.raw, "target-bin", self.inputs, self.external,
        )
        projected[0]["input_ordinal"] = False
        with self.assertRaisesRegex(ValueError, "input_binding"):
            validate_link_occurrence_authority(
                [{"target_id": "target-bin", "kind": "link",
                  "ordered_inputs": self.inputs,
                  "ordered_link_arguments": ["-lm"],
                  "ordered_link_occurrences": projected,
                  "ordered_link_search_roots": project_link_search_roots(self.raw)}],
                self.external,
            )

        projected = project_link_occurrences(
            self.raw, "target-bin", self.inputs, self.external,
        )
        projected[3]["argument_index"] = 5
        projected[4]["argument_index"] = 6
        with self.assertRaisesRegex(ValueError, "external"):
            validate_link_occurrence_authority(
                [{"target_id": "target-bin", "kind": "link",
                  "ordered_inputs": self.inputs,
                  "ordered_link_arguments": ["-lm"],
                  "ordered_link_occurrences": projected,
                  "ordered_link_search_roots": project_link_search_roots(self.raw)}],
                self.external,
            )

        projected = project_link_occurrences(
            self.raw, "target-bin", self.inputs, self.external,
        )
        with self.assertRaisesRegex(ValueError, "search_root_closure"):
            validate_link_occurrence_authority(
                [{"target_id": "target-bin", "kind": "link",
                  "ordered_inputs": self.inputs,
                  "ordered_link_arguments": ["-lm"],
                  "ordered_link_occurrences": projected,
                  "ordered_link_search_roots": []}],
                self.external,
            )

    def test_legacy_target_without_authority_remains_reopenable(self) -> None:
        validate_link_occurrence_authority(
            [{"target_id": "legacy", "kind": "link",
              "ordered_inputs": [], "ordered_link_arguments": []}],
            [],
        )

    def test_nonmaterialized_make_bindings_are_hashed_without_fabrication(self) -> None:
        binding = {
            "path": "build/unit.o", "kind": "file", "materialized": False,
        }
        inputs = [{
            "ordinal": 0, "role": "link-input", "binding": binding,
            "dependency_target_id": "object-unit",
        }]
        raw = {
            "inputs": [binding],
            "search_roots": [{
                "path": "build/lib", "kind": "directory",
                "materialized": False,
            }],
            "ordered_system_link_args": [],
            "external_native_libraries": [],
            "ordered_link_occurrences": [
                _raw(0, 0, 1, "input", 0),
                _raw(1, 1, 1, "search-root", 0),
            ],
        }
        projected = project_link_occurrences(
            raw, "target-bin", inputs, [],
        )
        target = {
            "target_id": "target-bin", "kind": "link",
            "ordered_inputs": inputs, "ordered_link_arguments": [],
            "ordered_link_occurrences": projected,
            "ordered_link_search_roots": project_link_search_roots(raw),
        }
        validate_link_occurrence_authority([target], [])


def _raw(
    ordinal: int, argument_index: int, argument_count: int,
    kind: str, reference_ordinal: int,
) -> dict:
    return {
        "ordinal": ordinal, "argument_index": argument_index,
        "argument_count": argument_count, "kind": kind,
        "reference_ordinal": reference_ordinal,
    }


def _file(path: str) -> dict:
    return {
        "path": path, "kind": "file", "materialized": True,
        "sha256": SHA, "size_bytes": 1,
    }


def _directory(path: str) -> dict:
    return {
        "path": path, "kind": "directory", "materialized": True,
        "sha256": SHA, "size_bytes": 1, "entry_count": 1,
    }


if __name__ == "__main__":
    unittest.main()
