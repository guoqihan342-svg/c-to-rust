from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.rust_occurrence_manifest import (
    inspect_occurrence_manifest, occurrence_manifest_bytes,
    render_occurrence_manifest_static,
)
from validation.tools.project_migration_rust_link_product_test_support import (
    ET_EXEC, ar_member, archive, elf_product, relocatable_elf,
)


def target() -> dict:
    return {
        "target_id": "target-generic",
        "input_occurrences": [
            {
                "ordinal": 0, "role": "link-input",
                "dependency_target_id": None,
                "binding_sha256": "a" * 64,
                "occurrence_id": "occurrence-a",
                "object_target_id": "object-a",
                "source_unit_id": "source-a", "module_id": "module-a",
            },
            {
                "ordinal": 1, "role": "link-input",
                "dependency_target_id": "target-library",
                "binding_sha256": "b" * 64,
                "occurrence_id": "occurrence-b",
                "object_target_id": None,
                "source_unit_id": None, "module_id": None,
            },
        ],
    }


class RustOccurrenceManifestTests(unittest.TestCase):
    def test_static_and_elf_scan_bind_order(self) -> None:
        value = target()
        marker = occurrence_manifest_bytes(value)
        lines = render_occurrence_manifest_static(value)
        self.assertTrue(any("#[used]" in line for line in lines))
        self.assertTrue(any("link_section" in line for line in lines))
        product = elf_product(ET_EXEC) + marker
        inspection = inspect_occurrence_manifest(
            product, value, object_format="elf",
        )
        self.assertEqual(2, inspection["occurrence_count"])
        self.assertIsNone(inspection["archive_member_ordinal"])

    def test_archive_scan_binds_containing_member(self) -> None:
        value = target()
        marker = occurrence_manifest_bytes(value)
        product = archive(
            ar_member("first.o/", relocatable_elf()),
            ar_member("bound.o/", relocatable_elf(suffix=marker)),
        )
        inspection = inspect_occurrence_manifest(
            product, value, object_format="unix-ar",
        )
        self.assertEqual(1, inspection["archive_member_ordinal"])
        self.assertIsNotNone(inspection["archive_member_name_sha256"])

    def test_duplicate_or_reordered_marker_does_not_pass(self) -> None:
        value = target()
        marker = occurrence_manifest_bytes(value)
        with self.assertRaises(ValueError):
            inspect_occurrence_manifest(
                elf_product(ET_EXEC) + marker + marker,
                value, object_format="elf",
            )
        reordered = copy.deepcopy(value)
        reordered["input_occurrences"].reverse()
        for ordinal, occurrence in enumerate(reordered["input_occurrences"]):
            occurrence["ordinal"] = ordinal
        with self.assertRaises(ValueError):
            inspect_occurrence_manifest(
                elf_product(ET_EXEC) + marker,
                reordered, object_format="elf",
            )


if __name__ == "__main__":
    unittest.main()
