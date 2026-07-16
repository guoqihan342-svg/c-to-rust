from __future__ import annotations

import copy
import hashlib
import json
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.rust_link_product_inspection import (
    inspect_rust_link_product,
    inspect_rust_link_product_bytes,
    reopen_rust_link_product_inspection,
    validate_rust_link_product_inspection,
)
from validation.tools.project_migration_rust_link_product_test_support import (
    ET_EXEC,
    OBJECT_KINDS,
    REPORT_FIELDS,
    ar_member,
    archive,
    elf_product,
    product_cases,
    relocatable_elf,
)


class RustLinkProductInspectionTests(unittest.TestCase):
    def test_valid_products_emit_canonical_path_free_reports(self) -> None:
        for label, data, product_kind, elf_type, pie, members in product_cases():
            with self.subTest(label=label):
                report = inspect_rust_link_product(data, product_kind)
                self.assertEqual(REPORT_FIELDS, set(report))
                self.assertEqual(product_kind, report["product_kind"])
                self.assertEqual(OBJECT_KINDS[product_kind], report["object_kind"])
                self.assertEqual(elf_type, report["elf_type"])
                self.assertIs(pie, report["pie"])
                self.assertEqual(members, report["member_count"])
                self.assertEqual(
                    hashlib.sha256(data).hexdigest(), report["file_sha256"],
                )
                self.assertEqual(len(data), report["size_bytes"])
                self.assertIs(report["semantic_gate"], False)
                self.assertEqual(0, report["translation_coverage_numerator"])
                self.assertNotIn("path", report)
                serialized = json.dumps(report, sort_keys=True)
                self.assertNotRegex(
                    serialized, r"[A-Za-z]:\\\\|/(?:home|root|tmp)/",
                )
                core = {
                    key: value for key, value in report.items()
                    if key != "inspection_sha256"
                }
                self.assertEqual(
                    content_sha256(core), report["inspection_sha256"],
                )
                self.assertEqual(
                    report, validate_rust_link_product_inspection(report),
                )
                self.assertEqual(
                    report, inspect_rust_link_product_bytes(data, product_kind),
                )
                self.assertEqual(
                    report, reopen_rust_link_product_inspection(data, report),
                )

    def test_valid_product_bytes_are_deterministic_and_order_bound(self) -> None:
        relocatable = relocatable_elf()
        first = archive(
            ar_member("first.o/", relocatable + b"first"),
            ar_member("second.o/", relocatable + b"second"),
        )
        second = archive(
            ar_member("second.o/", relocatable + b"second"),
            ar_member("first.o/", relocatable + b"first"),
        )
        first_report = inspect_rust_link_product(first, "staticlib")
        self.assertEqual(
            first_report, inspect_rust_link_product(first, "staticlib"),
        )
        self.assertNotEqual(
            first_report["member_identity_sha256"],
            inspect_rust_link_product(second, "staticlib")[
                "member_identity_sha256"
            ],
        )

    def test_gnu_long_name_table_newline_padding_is_unambiguous(self) -> None:
        names = b"very-long-object-name.o/\n"
        self.assertEqual(1, len(names) % 2)
        name_table = bytearray(ar_member("//", names + b"\n"))
        name_table[16:48] = b" " * 32
        data = archive(
            bytes(name_table),
            ar_member("/0", relocatable_elf()),
        )
        report = inspect_rust_link_product(data, "staticlib")
        self.assertEqual(1, report["member_count"])
        self.assertEqual(hashlib.sha256(data).hexdigest(), report["file_sha256"])

    def test_report_and_product_hash_drift_are_rejected(self) -> None:
        executable = elf_product(ET_EXEC)
        report = inspect_rust_link_product(executable, "bin")

        for key in ("file_sha256", "inspection_sha256"):
            tampered = copy.deepcopy(report)
            tampered[key] = "0" * 64
            with self.subTest(key=key), self.assertRaisesRegex(
                ValueError, "inspection_sha256_drift",
            ):
                validate_rust_link_product_inspection(tampered)

        with self.assertRaisesRegex(ValueError, "reopen_drift"):
            reopen_rust_link_product_inspection(executable + b"drift", report)


if __name__ == "__main__":
    unittest.main()
