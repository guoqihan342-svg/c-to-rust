from __future__ import annotations

from copy import deepcopy
import json
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.native_target_abi import (
    compare_native_target_abi,
    validate_native_target_abi,
)


def _inspection(
    machine: int,
    class_bits: int,
    endianness: str,
    seed: str,
    *,
    object_format: str = "elf",
) -> dict[str, object]:
    member_count = 1 if object_format == "elf" else 2
    core = {
        "schema_version": 1,
        "artifact_kind": "native-object-inspection",
        "object_format": object_format,
        "object_kind": (
            "shared-object" if object_format == "elf" else "static-archive"
        ),
        "machine": machine,
        "class_bits": class_bits,
        "endianness": endianness,
        "member_count": member_count,
        "member_identity_sha256": content_sha256(["members", seed]),
        "file_sha256": content_sha256(["file", seed]),
        "size_bytes": 64 + len(seed),
        "semantic_gate": False,
    }
    return {**core, "inspection_sha256": content_sha256(core)}


def _refresh_report_hash(report: dict[str, object]) -> None:
    core = {key: value for key, value in report.items() if key != "report_sha256"}
    report["report_sha256"] = content_sha256(core)


class NativeTargetAbiTests(unittest.TestCase):
    def test_supported_linux_target_matrix_and_aliases(self) -> None:
        cases = [
            ("x86_64-linux-gnu", "x86_64", 62, 64, "little"),
            ("amd64-unknown-linux-musl", "x86_64", 62, 64, "little"),
            ("i686-pc-linux-gnu", "i386", 3, 32, "little"),
            ("aarch64-linux-gnu", "aarch64", 183, 64, "little"),
            ("aarch64_be-linux-gnu", "aarch64", 183, 64, "big"),
            ("arm-linux-gnueabihf", "arm", 40, 32, "little"),
            ("armv7l-unknown-linux-gnueabi", "arm", 40, 32, "little"),
            ("armeb-linux-gnueabi", "arm", 40, 32, "big"),
            ("riscv32-linux-gnu", "riscv32", 243, 32, "little"),
            ("riscv64-linux-gnu", "riscv64", 243, 64, "little"),
            ("s390x-linux-gnu", "s390x", 22, 64, "big"),
            ("powerpc-linux-gnu", "powerpc", 20, 32, "big"),
            ("ppc-linux-gnu", "powerpc", 20, 32, "big"),
            ("powerpc64-linux-gnu", "powerpc64", 21, 64, "big"),
            ("powerpc64le-linux-gnu", "powerpc64", 21, 64, "little"),
            ("ppc64le-unknown-linux-gnu", "powerpc64", 21, 64, "little"),
            ("mips-linux-gnu", "mips", 8, 32, "big"),
            ("mipsel-linux-gnu", "mips", 8, 32, "little"),
            ("mips64-linux-gnuabi64", "mips64", 8, 64, "big"),
            ("mips64el-linux-gnuabi64", "mips64", 8, 64, "little"),
            ("loongarch64-linux-gnu", "loongarch64", 258, 64, "little"),
        ]
        for target, architecture, machine, bits, endian in cases:
            with self.subTest(target=target):
                inspection = _inspection(machine, bits, endian, target)
                report = compare_native_target_abi(target, inspection)
                self.assertTrue(report["abi_gate"])
                self.assertFalse(report["semantic_gate"])
                self.assertEqual(architecture, report["expected_abi"]["architecture"])
                self.assertEqual(report, validate_native_target_abi(report))

    def test_multiple_inspections_are_stable_path_free_and_all_required(self) -> None:
        shared = _inspection(62, 64, "little", "shared")
        archive = _inspection(
            62, 64, "little", "archive", object_format="unix-ar",
        )
        first = compare_native_target_abi(
            "x86_64-pc-linux-gnu", [shared, archive],
        )
        second = compare_native_target_abi(
            "x86_64-pc-linux-gnu", [archive, shared],
        )
        self.assertEqual(first, second)
        self.assertEqual(2, first["inspection_count"])
        self.assertRegex(first["report_sha256"], r"^[0-9a-f]{64}$")
        encoded = json.dumps(first, sort_keys=True)
        self.assertNotIn('"path"', encoded)
        self.assertNotIn('"link_gate"', encoded)

    def test_mixed_abi_fails_only_the_abi_gate(self) -> None:
        matching = _inspection(62, 64, "little", "matching")
        wrong = _inspection(3, 32, "little", "wrong")
        report = compare_native_target_abi(
            "x86_64-linux-gnu", [matching, wrong],
        )
        self.assertFalse(report["abi_gate"])
        self.assertFalse(report["semantic_gate"])
        failed = [item for item in report["checks"] if not item["abi_match"]]
        self.assertEqual(1, len(failed))
        self.assertEqual(["machine", "class_bits"], failed[0]["mismatches"])
        self.assertEqual(report, validate_native_target_abi(report))

    def test_tampering_is_rejected_even_when_outer_hash_is_refreshed(self) -> None:
        report = compare_native_target_abi(
            "x86_64-linux-gnu", _inspection(62, 64, "little", "base"),
        )
        nested = deepcopy(report)
        nested["checks"][0]["inspection"]["machine"] = 183
        _refresh_report_hash(nested)
        with self.assertRaisesRegex(ValueError, "native_object_inspection_sha256_drift"):
            validate_native_target_abi(nested)

        gate = deepcopy(report)
        gate["abi_gate"] = False
        _refresh_report_hash(gate)
        with self.assertRaisesRegex(ValueError, "native_target_abi_summary_invalid"):
            validate_native_target_abi(gate)

        check = deepcopy(report)
        check["checks"][0]["mismatches"] = ["machine"]
        check["checks"][0]["abi_match"] = False
        check["abi_gate"] = False
        _refresh_report_hash(check)
        with self.assertRaisesRegex(ValueError, "native_target_abi_check_invalid"):
            validate_native_target_abi(check)

    def test_unknown_ambiguous_and_non_linux_targets_fail_closed(self) -> None:
        inspection = _inspection(62, 64, "little", "target-errors")
        cases = [
            ("sparc64-linux-gnu", "unsupported"),
            ("x86_64-aarch64-linux-gnu", "ambiguous"),
            ("x86_64-linux-gnux32", "ambiguous"),
            ("mips64el-linux-gnuabin32", "ambiguous"),
            ("x86_64-pc-windows-gnu", "linux_target_required"),
            ("X86_64-linux-gnu", "target_triple_invalid"),
        ]
        for target, reason in cases:
            with self.subTest(target=target):
                with self.assertRaisesRegex(ValueError, reason):
                    compare_native_target_abi(target, inspection)

    def test_empty_and_duplicate_inspection_sets_fail_closed(self) -> None:
        inspection = _inspection(62, 64, "little", "duplicate")
        with self.assertRaisesRegex(ValueError, "inspections_invalid"):
            compare_native_target_abi("x86_64-linux-gnu", [])
        with self.assertRaisesRegex(ValueError, "duplicate_inspection"):
            compare_native_target_abi(
                "x86_64-linux-gnu", [inspection, inspection],
            )


if __name__ == "__main__":
    unittest.main()
