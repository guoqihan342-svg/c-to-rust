from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

from validation.tools._project_migration_harness import native_object_inspection
from validation.tools._project_migration_harness.native_object_inspection import (
    MAX_NATIVE_OBJECT_BYTES, inspect_native_object,
)
from validation.tools._project_migration_harness.native_object_validation import (
    validate_native_object_inspection,
)


_REPORT_FIELDS = {
    "schema_version", "artifact_kind",
    "object_format", "object_kind", "machine", "class_bits", "endianness",
    "member_count", "member_identity_sha256", "file_sha256", "size_bytes",
    "semantic_gate", "inspection_sha256",
}


def _elf(
    class_bits: int,
    endianness: str,
    *,
    object_type: int,
    machine: int,
    suffix: bytes = b"",
) -> bytes:
    prefix = "<" if endianness == "little" else ">"
    class_code = 1 if class_bits == 32 else 2
    data_code = 1 if endianness == "little" else 2
    ident = b"\x7fELF" + bytes((class_code, data_code, 1, 0, 0)) + b"\x00" * 7
    if class_bits == 32:
        header = struct.pack(
            prefix + "HHIIIIIHHHHHH",
            object_type, machine, 1, 0, 0, 0, 0, 52, 32, 0, 40, 0, 0,
        )
    else:
        header = struct.pack(
            prefix + "HHIQQQIHHHHHH",
            object_type, machine, 1, 0, 0, 0, 0, 64, 56, 0, 64, 0, 0,
        )
    return ident + header + suffix


def _ar_member(
    token: str,
    payload: bytes,
    *,
    declared_size: int | None = None,
    padding: bytes = b"\n",
) -> bytes:
    encoded = token.encode("ascii")
    if len(encoded) > 16:
        raise AssertionError("test ar token is too long")
    size = len(payload) if declared_size is None else declared_size
    fields = (
        encoded.ljust(16, b" "),
        b"0".ljust(12, b" "),
        b"0".ljust(6, b" "),
        b"0".ljust(6, b" "),
        b"100644".ljust(8, b" "),
        str(size).encode("ascii").ljust(10, b" "),
        b"`\n",
    )
    result = b"".join(fields) + payload
    if size % 2:
        result += padding
    return result


def _archive(*members: bytes) -> bytes:
    return b"!<arch>\n" + b"".join(members)


class NativeObjectInspectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="native-object-test-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, name: str, data: bytes) -> Path:
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_shared_elf_32_64_little_and_big_endian(self) -> None:
        cases = (
            (32, "little", 3),
            (32, "big", 8),
            (64, "little", 62),
            (64, "big", 183),
        )
        for index, (class_bits, endianness, machine) in enumerate(cases):
            data = _elf(
                class_bits, endianness, object_type=3, machine=machine,
            )
            path = self.write(f"shared-{index}.bin", data)
            with self.subTest(class_bits=class_bits, endianness=endianness):
                report = inspect_native_object(path)
                self.assertEqual(_REPORT_FIELDS, set(report))
                self.assertEqual("elf", report["object_format"])
                self.assertEqual("shared-object", report["object_kind"])
                self.assertEqual(class_bits, report["class_bits"])
                self.assertEqual(endianness, report["endianness"])
                self.assertEqual(machine, report["machine"])
                self.assertEqual(1, report["member_count"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), report["file_sha256"])
                self.assertEqual(len(data), report["size_bytes"])
                self.assertRegex(report["member_identity_sha256"], r"^[0-9a-f]{64}$")

    def test_shared_object_requires_et_dyn_and_complete_valid_header(self) -> None:
        invalid = (
            (b"not-elf", "format_invalid"),
            (b"\x7fELF\x02\x01\x01", "header_truncated"),
            (_elf(64, "little", object_type=1, machine=62), "type_invalid"),
            (_elf(64, "little", object_type=2, machine=62), "type_invalid"),
            (_elf(64, "little", object_type=3, machine=0), "machine_invalid"),
        )
        for index, (data, error) in enumerate(invalid):
            path = self.write(f"invalid-elf-{index}", data)
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                inspect_native_object(path)

    def test_single_and_multiple_member_archives_are_deterministic(self) -> None:
        first = _elf(64, "little", object_type=1, machine=62, suffix=b"first")
        second = _elf(64, "little", object_type=1, machine=62, suffix=b"second")
        single_data = _archive(_ar_member("first.o/", first))
        single = inspect_native_object(self.write("single.a", single_data))
        self.assertEqual("unix-ar", single["object_format"])
        self.assertEqual("static-archive", single["object_kind"])
        self.assertEqual(1, single["member_count"])
        multi_data = _archive(
            _ar_member("first.o/", first), _ar_member("second.o/", second),
        )
        path = self.write("multi.a", multi_data)
        multi = inspect_native_object(path)
        self.assertEqual(2, multi["member_count"])
        self.assertEqual(multi, inspect_native_object(path))
        reversed_data = _archive(
            _ar_member("second.o/", second), _ar_member("first.o/", first),
        )
        reversed_report = inspect_native_object(self.write("reversed.a", reversed_data))
        self.assertNotEqual(
            multi["member_identity_sha256"],
            reversed_report["member_identity_sha256"],
        )

    def test_gnu_long_names_and_symbol_index_are_supported(self) -> None:
        first_name = b"very-long-first-object-name.o"
        second_name = b"another-long-object-name.o"
        table = first_name + b"/\n" + second_name + b"/\n"
        second_offset = len(first_name) + 2
        data = _archive(
            _ar_member("/", b"index"),
            _ar_member("//", table),
            _ar_member("/0", _elf(32, "little", object_type=1, machine=3)),
            _ar_member(
                f"/{second_offset}",
                _elf(32, "little", object_type=1, machine=3, suffix=b"two"),
            ),
        )
        report = inspect_native_object(self.write("gnu.a", data))
        self.assertEqual(2, report["member_count"])
        self.assertEqual((32, "little", 3), (
            report["class_bits"], report["endianness"], report["machine"],
        ))

    def test_bsd_extended_name_and_symbol_index_are_supported(self) -> None:
        name = b"bsd-extended-object-name.o"
        obj = _elf(64, "big", object_type=1, machine=183)
        data = _archive(
            _ar_member("__.SYMDEF/", b"index"),
            _ar_member(f"#1/{len(name)}", name + obj),
        )
        report = inspect_native_object(self.write("bsd.a", data))
        self.assertEqual(1, report["member_count"])
        self.assertEqual(64, report["class_bits"])
        self.assertEqual("big", report["endianness"])
        self.assertEqual(183, report["machine"])

    def test_empty_mixed_abi_and_non_rel_archives_are_rejected(self) -> None:
        rel64 = _elf(64, "little", object_type=1, machine=62)
        invalid = (
            (_archive(), "archive_empty"),
            (_archive(_ar_member("/", b"index")), "archive_empty"),
            (_archive(
                _ar_member("one.o/", rel64),
                _ar_member("two.o/", _elf(32, "little", object_type=1, machine=3)),
            ), "mixed_abi"),
            (_archive(
                _ar_member("shared.o/", _elf(64, "little", object_type=3, machine=62)),
            ), "type_invalid"),
        )
        for index, (data, error) in enumerate(invalid):
            path = self.write(f"invalid-archive-{index}.a", data)
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                inspect_native_object(path)

    def test_archive_bounds_padding_references_and_duplicates_fail_closed(self) -> None:
        obj = _elf(64, "little", object_type=1, machine=62)
        malformed = (
            (_archive(b"short"), "header_truncated"),
            (_archive(_ar_member("one.o/", obj, declared_size=len(obj) + 2)),
             "member_out_of_bounds"),
            (_archive(_ar_member("odd.o/", obj + b"x", padding=b"x")),
             "padding_invalid"),
            (_archive(_ar_member("/9", obj)), "name_reference_invalid"),
            (_archive(
                _ar_member("same.o/", obj), _ar_member("same.o/", obj + b"x"),
            ), "duplicate_member"),
            (_archive(
                _ar_member("/", b"one"), _ar_member("/SYM64/", b"two"),
                _ar_member("one.o/", obj),
            ), "duplicate_symbol_index"),
        )
        for index, (data, error) in enumerate(malformed):
            path = self.write(f"malformed-{index}.a", data)
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                inspect_native_object(path)

    def test_stable_read_limit_non_regular_and_toctou_fail_closed(self) -> None:
        data = _elf(64, "little", object_type=3, machine=62)
        path = self.write("bounded.so", data)
        with self.assertRaisesRegex(ValueError, "stable_file_invalid"):
            inspect_native_object(path, limit=len(data) - 1)
        with self.assertRaisesRegex(ValueError, "native_object_limit_invalid"):
            inspect_native_object(path, limit=MAX_NATIVE_OBJECT_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "stable_file_"):
            inspect_native_object(self.root)
        with mock.patch.object(
            native_object_inspection,
            "read_stable_file",
            side_effect=ValueError("stable_file_changed_while_reading"),
        ):
            with self.assertRaisesRegex(ValueError, "changed_while_reading"):
                inspect_native_object(path)

    def test_report_contains_no_path_and_binds_file_bytes(self) -> None:
        obj = _elf(64, "little", object_type=1, machine=62)
        data = _archive(_ar_member("object.o/", obj))
        path = self.write("private-name.a", data)
        report = inspect_native_object(path)
        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn(path.name, serialized)
        self.assertEqual(hashlib.sha256(data).hexdigest(), report["file_sha256"])
        self.assertEqual(_REPORT_FIELDS, set(report))

    def test_report_reopen_validation_rejects_tampering(self) -> None:
        data = _elf(64, "little", object_type=3, machine=62)
        report = inspect_native_object(self.write("validated.so", data))
        self.assertEqual(report, validate_native_object_inspection(report))

        mutations = (
            ("object_kind", "static-archive", "summary_invalid"),
            ("member_count", 2, "summary_invalid"),
            ("file_sha256", "g" * 64, "summary_invalid"),
            ("inspection_sha256", "0" * 64, "sha256_drift"),
        )
        for key, value, error in mutations:
            tampered = copy.deepcopy(report)
            tampered[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, error):
                validate_native_object_inspection(tampered)


if __name__ == "__main__":
    unittest.main()
