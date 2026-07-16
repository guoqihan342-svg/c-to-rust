from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.rust_link_product_inspection import (
    MAX_RUST_LINK_PRODUCT_BYTES,
    inspect_rust_link_product,
    validate_rust_link_product_inspection,
)
from validation.tools.project_migration_rust_link_product_test_support import (
    ET_DYN,
    ET_EXEC,
    ar_member,
    archive,
    elf_product,
    product_cases,
    relocatable_elf,
)


class RustLinkProductInspectionFailClosedTests(unittest.TestCase):
    def test_product_type_mismatches_fail_closed(self) -> None:
        products = {
            label: data for label, data, _kind, *_rest in product_cases()
        }
        cases = (
            (products["et-exec"], "cdylib"),
            (products["cdylib"], "bin"),
            (products["staticlib"], "rlib"),
            (products["rlib"], "staticlib"),
        )
        for data, wrong_type in cases:
            with self.subTest(wrong_type=wrong_type), self.assertRaisesRegex(
                ValueError, "rust_link_product_type_mismatch",
            ):
                inspect_rust_link_product(data, wrong_type)

    def test_structurally_ambiguous_products_are_rejected(self) -> None:
        unmarked_dynamic_executable = elf_product(
            ET_DYN, executable_entry=True,
        )
        with self.assertRaisesRegex(ValueError, "layout_ambiguous"):
            inspect_rust_link_product(unmarked_dynamic_executable, "bin")

        relocatable = relocatable_elf()
        metadata_not_first = archive(
            ar_member("unit.o/", relocatable),
            ar_member("lib.rmeta/", relocatable + b"metadata"),
        )
        with self.assertRaisesRegex(ValueError, "metadata_ambiguous"):
            inspect_rust_link_product(metadata_not_first, "rlib")

    def test_truncation_and_byte_limits_fail_closed(self) -> None:
        executable = elf_product(ET_EXEC)
        pie = elf_product(ET_DYN, interpreter=True)
        relocatable = relocatable_elf()
        truncated_archive = archive(ar_member(
            "unit.o/", relocatable, declared_size=len(relocatable) + 8,
        ))
        cases = (
            (executable[:40], "bin"),
            (pie[:-1], "bin"),
            (truncated_archive, "staticlib"),
        )
        for data, product_kind in cases:
            with self.subTest(product_kind=product_kind), self.assertRaisesRegex(
                ValueError, "truncated|out_of_bounds",
            ):
                inspect_rust_link_product(data, product_kind)

        with self.assertRaisesRegex(ValueError, "bytes_invalid"):
            inspect_rust_link_product(
                executable, "bin", limit=len(executable) - 1,
            )
        with self.assertRaisesRegex(ValueError, "limit_invalid"):
            inspect_rust_link_product(
                executable, "bin", limit=MAX_RUST_LINK_PRODUCT_BYTES + 1,
            )
        with self.assertRaisesRegex(ValueError, "bytes_invalid"):
            inspect_rust_link_product(
                bytearray(executable), "bin",  # type: ignore[arg-type]
            )

    def test_report_non_scalar_shape_is_rejected_as_value_error(self) -> None:
        report = inspect_rust_link_product(elf_product(ET_EXEC), "bin")
        for key in ("object_format", "elf_type", "class_bits", "endianness"):
            malformed = copy.deepcopy(report)
            malformed[key] = []
            with self.subTest(key=key), self.assertRaisesRegex(
                ValueError, "rust_link_product_report_invalid",
            ):
                validate_rust_link_product_inspection(malformed)

    def test_member_schema_and_legacy_reports_fail_closed(self) -> None:
        payload = relocatable_elf()
        report = inspect_rust_link_product(
            archive(ar_member("unit.o/", payload)), "staticlib",
        )
        cases = []
        legacy = copy.deepcopy(report)
        legacy["schema_version"] = 1
        cases.append(legacy)
        non_list = copy.deepcopy(report)
        non_list["members"] = {}
        cases.append(non_list)
        for key, value in (
            ("ordinal", 1),
            ("member_name_sha256", "not-a-sha"),
            ("elf_type", "ET_DYN"),
            ("machine", 3),
            ("endianness", []),
        ):
            malformed = copy.deepcopy(report)
            malformed["members"][0][key] = value
            cases.append(malformed)
        unexpected = copy.deepcopy(report)
        unexpected["members"][0]["member_name"] = "unit.o"
        cases.append(unexpected)
        for malformed in cases:
            with self.subTest(malformed=malformed), self.assertRaisesRegex(
                ValueError, "rust_link_product_report_invalid",
            ):
                validate_rust_link_product_inspection(malformed)

    def test_duplicate_members_do_not_hide_duplicate_symbol_indexes(self) -> None:
        payload = relocatable_elf()
        data = archive(
            ar_member("same.o/", payload), ar_member("same.o/", payload),
            ar_member("/", b"first-index"), ar_member("/", b"second-index"),
        )
        with self.assertRaisesRegex(ValueError, "duplicate_symbol_index"):
            inspect_rust_link_product(data, "staticlib")


if __name__ == "__main__":
    unittest.main()
