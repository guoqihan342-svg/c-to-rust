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
                self.assertEqual(2, report["schema_version"])
                self.assertEqual(product_kind, report["product_kind"])
                self.assertEqual(OBJECT_KINDS[product_kind], report["object_kind"])
                self.assertEqual(elf_type, report["elf_type"])
                self.assertIs(pie, report["pie"])
                self.assertEqual(members, report["member_count"])
                self.assertEqual(members, len(report["members"]))
                self.assertEqual(
                    content_sha256(report["members"]),
                    report["member_identity_sha256"],
                )
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
        first_payload = relocatable + b"first"
        second_payload = relocatable + b"second"
        first = archive(
            ar_member("first.o/", first_payload),
            ar_member("second.o/", second_payload),
        )
        second = archive(
            ar_member("second.o/", second_payload),
            ar_member("first.o/", first_payload),
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
        self.assertEqual([0, 1], [item["ordinal"] for item in first_report["members"]])
        self.assertEqual(
            [hashlib.sha256(name).hexdigest() for name in (b"first.o", b"second.o")],
            [item["member_name_sha256"] for item in first_report["members"]],
        )
        self.assertEqual(
            [hashlib.sha256(payload).hexdigest()
             for payload in (first_payload, second_payload)],
            [item["payload_sha256"] for item in first_report["members"]],
        )

    def test_duplicate_members_are_preserved_without_disclosing_names(self) -> None:
        payload = relocatable_elf()
        data = archive(
            ar_member("private.o/", payload), ar_member("private.o/", payload),
        )
        report = inspect_rust_link_product(data, "staticlib")
        self.assertEqual(2, report["member_count"])
        self.assertEqual([0, 1], [item["ordinal"] for item in report["members"]])
        self.assertEqual(
            report["members"][0]["member_name_sha256"],
            report["members"][1]["member_name_sha256"],
        )
        self.assertEqual(
            report["members"][0]["payload_sha256"],
            report["members"][1]["payload_sha256"],
        )
        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn("private.o", serialized)
        self.assertNotRegex(serialized, r"[A-Za-z]:\\\\|/(?:home|root|tmp)/")

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

    def test_self_consistent_member_tampering_fails_closed(self) -> None:
        payload = relocatable_elf()
        data = archive(
            ar_member("first.o/", payload + b"first"),
            ar_member("second.o/", payload + b"second"),
        )
        report = inspect_rust_link_product(data, "staticlib")
        cases = {}

        forged_name = copy.deepcopy(report)
        forged_name["members"][0]["member_name_sha256"] = "0" * 64
        cases["forged-name"] = _reseal(forged_name)

        forged_payload = copy.deepcopy(report)
        forged_payload["members"][0]["payload_sha256"] = "1" * 64
        cases["forged-payload"] = _reseal(forged_payload)

        reversed_members = copy.deepcopy(report)
        reversed_members["members"].reverse()
        for ordinal, member in enumerate(reversed_members["members"]):
            member["ordinal"] = ordinal
        cases["reversed"] = _reseal(reversed_members)

        removed = copy.deepcopy(report)
        removed["members"].pop()
        removed["member_count"] = len(removed["members"])
        cases["removed"] = _reseal(removed)

        added = copy.deepcopy(report)
        extra = copy.deepcopy(added["members"][-1])
        extra["ordinal"] = len(added["members"])
        added["members"].append(extra)
        added["member_count"] = len(added["members"])
        cases["added"] = _reseal(added)

        abi_drift = copy.deepcopy(report)
        abi_drift["machine"] = 3
        for member in abi_drift["members"]:
            member["machine"] = 3
        cases["abi-drift"] = _reseal(abi_drift)

        for label, tampered in cases.items():
            with self.subTest(label=label):
                self.assertEqual(tampered, validate_rust_link_product_inspection(tampered))
                with self.assertRaisesRegex(ValueError, "reopen_drift"):
                    reopen_rust_link_product_inspection(data, tampered)

        out_of_order = copy.deepcopy(report)
        out_of_order["members"].reverse()
        _reseal(out_of_order)
        with self.assertRaisesRegex(ValueError, "report_invalid"):
            validate_rust_link_product_inspection(out_of_order)


def _reseal(report: dict) -> dict:
    report["member_identity_sha256"] = content_sha256(report["members"])
    core = {key: value for key, value in report.items() if key != "inspection_sha256"}
    report["inspection_sha256"] = content_sha256(core)
    return report


if __name__ == "__main__":
    unittest.main()
