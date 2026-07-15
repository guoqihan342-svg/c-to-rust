from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools._project_migration_harness import native_object_symbols
from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.native_object_symbols import (
    MAX_NATIVE_OBJECT_BYTES,
    MAX_SYMBOL_NAME_BYTES,
    MAX_SYMBOL_SET_UTF8_BYTES,
    extract_native_object_symbols,
    reopen_native_object_symbols,
    validate_native_object_symbols,
)
from validation.tools.project_migration_native_object_symbols_test_support import (
    Symbol,
    ar_member,
    archive,
    duplicate_archives,
    elf_object,
    indexed_archives,
    invalid_symbol_boundary_objects,
    overflowing_symbols,
    patch_section,
    patch_section_table_offset,
    patch_symbol_name,
)


class NativeObjectSymbolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="native-symbols-test-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, name: str, data: bytes) -> Path:
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_shared_elf_matrix_filters_and_deduplicates_exports(self) -> None:
        symbols = [
            Symbol("zeta"),
            Symbol("alpha", binding=2, visibility=3),
            Symbol("undefined", defined=False),
            Symbol("local", binding=0),
            Symbol("hidden", visibility=2),
            Symbol("internal", binding=2, visibility=1),
            Symbol("alpha", binding=2),
        ]
        cases = ((32, "little"), (32, "big"), (64, "little"), (64, "big"))
        for index, (bits, endian) in enumerate(cases):
            data = elf_object(
                bits, endian, object_type=3, tables=[("dynsym", symbols)],
            )
            with self.subTest(bits=bits, endian=endian):
                report = extract_native_object_symbols(
                    self.write(f"shared-{index}.so", data),
                )
                self.assertEqual(["alpha", "zeta"], report["symbols"])
                self.assertEqual(2, report["symbol_count"])
                self.assertEqual("elf", report["object_format"])
                self.assertEqual("shared-object", report["object_kind"])
                self.assertEqual(1, report["member_count"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), report["file_sha256"])
                self.assertEqual(content_sha256(["alpha", "zeta"]), report["symbol_set_sha256"])
                self.assertIs(report["semantic_gate"], False)

    def test_shared_prefers_dynsym_and_supports_symtab_fallback(self) -> None:
        preferred = elf_object(
            64, "little", object_type=3,
            tables=[
                ("dynsym", [Symbol("public")]),
                ("symtab", [Symbol("private_full_table")]),
            ],
        )
        report = extract_native_object_symbols(self.write("preferred.so", preferred))
        self.assertEqual(["public"], report["symbols"])

        fallback = elf_object(
            32, "big", object_type=3,
            tables=[("symtab", [Symbol("compat"), Symbol("not_defined", defined=False)])],
        )
        report = extract_native_object_symbols(self.write("fallback.so", fallback))
        self.assertEqual(["compat"], report["symbols"])

    def test_static_archive_accepts_mixed_elf_and_deduplicates(self) -> None:
        first = elf_object(
            32, "big", object_type=1,
            tables=[("symtab", [
                Symbol("first"), Symbol("dup", binding=2, visibility=2),
                Symbol("missing", defined=False),
                Symbol("absolute", section_index=0xFFF1),
                Symbol("common", section_index=0xFFF2),
            ])],
        )
        second = elf_object(
            64, "little", object_type=1,
            tables=[("symtab", [Symbol("second", binding=2), Symbol("dup")])],
        )
        data = archive(ar_member("first.o/", first), ar_member("second.o/", second))
        report = extract_native_object_symbols(self.write("mixed.a", data))
        self.assertEqual(
            ["absolute", "common", "dup", "first", "second"], report["symbols"],
        )
        self.assertEqual("unix-ar", report["object_format"])
        self.assertEqual("static-archive", report["object_kind"])
        self.assertEqual(2, report["member_count"])

    def test_gnu_and_bsd_archive_names_and_indexes(self) -> None:
        gnu_object = elf_object(
            64, "little", object_type=1,
            tables=[("symtab", [Symbol("gnu_export")])],
        )
        bsd_object = elf_object(
            32, "big", object_type=1,
            tables=[("symtab", [Symbol("bsd_export", binding=2)])],
        )
        for label, data in indexed_archives(gnu_object, bsd_object):
            expected = ["gnu_export"] if label.startswith("gnu") else ["bsd_export"]
            with self.subTest(label=label):
                report = extract_native_object_symbols(self.write(f"{label}.a", data))
                self.assertEqual(expected, report["symbols"])

    def test_archive_duplicate_names_tables_and_indexes_fail_closed(self) -> None:
        obj = elf_object(
            64, "little", object_type=1,
            tables=[("symtab", [Symbol("export")])],
        )
        for index, data in enumerate(duplicate_archives(obj)):
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "duplicate"):
                extract_native_object_symbols(self.write(f"duplicate-{index}.a", data))

    def test_malicious_section_and_string_offsets_fail_closed(self) -> None:
        base = elf_object(
            64, "little", object_type=3,
            tables=[("dynsym", [Symbol("safe")])],
        )
        malformed = [
            patch_section(base, 3, "offset", len(base) + 1),
            patch_section(base, 2, "size", len(base)),
            patch_section(base, 3, "link", 99),
            patch_section(base, 3, "entry_size", 1),
            patch_section(base, 3, "name", 99_999),
            patch_section_table_offset(base, len(base) + 1),
            patch_symbol_name(base, 3, 0, 1),
            elf_object(
                64, "little", object_type=3,
                tables=[("dynsym", [Symbol("bad", name_offset=99_999)])],
            ),
        ]
        for index, data in enumerate(malformed):
            with self.subTest(index=index), self.assertRaisesRegex(
                ValueError, "native_object_symbols_",
            ):
                extract_native_object_symbols(self.write(f"malicious-{index}.so", data))

    def test_symbol_name_set_budgets_and_section_indexes_fail_closed(self) -> None:
        normal = elf_object(64, "little", object_type=3, tables=[(
            "dynsym", [Symbol("normal")],
        )])
        baseline = extract_native_object_symbols(self.write("normal.so", normal))
        for index, data in enumerate(invalid_symbol_boundary_objects(
            MAX_SYMBOL_NAME_BYTES,
        )):
            with self.subTest(index=index), self.assertRaises(ValueError):
                extract_native_object_symbols(self.write(f"symbol-bound-{index}.so", data))

        overflowing = overflowing_symbols(MAX_SYMBOL_NAME_BYTES, MAX_SYMBOL_SET_UTF8_BYTES)
        oversized = elf_object(
            64, "little", object_type=3, tables=[("dynsym", overflowing)],
        )
        with self.assertRaisesRegex(ValueError, "symbol_budget_exceeded"):
            extract_native_object_symbols(self.write("symbol-set-too-large.so", oversized))
        for symbols in (
            ["x" * (MAX_SYMBOL_NAME_BYTES + 1)],
            [symbol.name for symbol in overflowing],
            ["\ud800"],
        ):
            changed = copy.deepcopy(baseline)
            changed["symbols"] = symbols
            changed["symbol_count"] = len(symbols)
            with self.assertRaisesRegex(ValueError, "report_invalid"):
                validate_native_object_symbols(changed)

    def test_malformed_archive_and_non_relocatable_member_fail_closed(self) -> None:
        rel = elf_object(
            64, "little", object_type=1,
            tables=[("symtab", [Symbol("ok")])],
        )
        shared = elf_object(
            64, "little", object_type=3,
            tables=[("dynsym", [Symbol("wrong_kind")])],
        )
        malformed = (
            archive(ar_member("bad.o/", rel, declared_size=len(rel) + 100)),
            archive(ar_member("/0", rel)),
            archive(ar_member("shared.o/", shared)),
            archive(ar_member("//", b"unterminated"), ar_member("/0", rel)),
        )
        for index, data in enumerate(malformed):
            with self.subTest(index=index), self.assertRaises(ValueError):
                extract_native_object_symbols(self.write(f"bad-{index}.a", data))

    def test_output_is_path_free_deterministic_and_read_bounded(self) -> None:
        data = elf_object(
            64, "little", object_type=3,
            tables=[("dynsym", [Symbol("stable")])],
        )
        first_path = self.write("private-first-name.so", data)
        second_path = self.write("private-second-name.so", data)
        first = extract_native_object_symbols(first_path)
        self.assertEqual(first, extract_native_object_symbols(first_path))
        self.assertEqual(first, extract_native_object_symbols(second_path))
        encoded = json.dumps(first, sort_keys=True)
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn(first_path.name, encoded)
        with self.assertRaisesRegex(ValueError, "stable_file_invalid"):
            extract_native_object_symbols(first_path, limit=len(data) - 1)
        with self.assertRaisesRegex(ValueError, "limit_invalid"):
            extract_native_object_symbols(first_path, limit=MAX_NATIVE_OBJECT_BYTES + 1)
        with mock.patch.object(
            native_object_symbols, "read_stable_file",
            side_effect=ValueError("stable_file_changed_while_reading"),
        ):
            with self.assertRaisesRegex(ValueError, "changed_while_reading"):
                extract_native_object_symbols(first_path)

    def test_validator_and_strict_reopen_reject_tampering(self) -> None:
        data = elf_object(
            64, "little", object_type=3,
            tables=[("dynsym", [Symbol("bound")])],
        )
        path = self.write("bound.so", data)
        report = extract_native_object_symbols(path)
        self.assertEqual(report, validate_native_object_symbols(report))
        self.assertEqual(report, reopen_native_object_symbols(path, report))

        changed = copy.deepcopy(report)
        changed["symbol_set_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "symbol_set_sha256_drift"):
            validate_native_object_symbols(changed)
        changed = copy.deepcopy(report)
        changed["report_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "report_sha256_drift"):
            validate_native_object_symbols(changed)
        for key, value in (("schema_version", True), ("object_format", [])):
            changed = copy.deepcopy(report)
            changed[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "report_invalid"):
                validate_native_object_symbols(changed)

        forged = copy.deepcopy(report)
        forged["symbols"] = ["bound", "forged"]
        forged["symbol_count"] = 2
        forged["symbol_set_sha256"] = content_sha256(forged["symbols"])
        forged["report_sha256"] = content_sha256({
            key: value for key, value in forged.items() if key != "report_sha256"
        })
        self.assertEqual(forged, validate_native_object_symbols(forged))
        with self.assertRaisesRegex(ValueError, "reopen_drift"):
            reopen_native_object_symbols(path, forged)

        replacement = elf_object(
            64, "little", object_type=3,
            tables=[("dynsym", [Symbol("replacement")])],
        )
        path.write_bytes(replacement)
        with self.assertRaisesRegex(ValueError, "reopen_drift"):
            reopen_native_object_symbols(path, report)

    def test_production_modules_are_pure_python_and_bounded_in_size(self) -> None:
        directory = Path(native_object_symbols.__file__).parent
        for name in (
            "native_object_symbols.py", "native_object_symbols_parsing.py",
            "native_object_symbols_archive.py",
        ):
            source = (directory / name).read_text(encoding="utf-8")
            self.assertLessEqual(len(source.splitlines()), 300, name)
            imports = {
                alias.name.split(".", 1)[0]
                for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.Import)
                for alias in node.names
            }
            self.assertNotIn("subprocess", imports)
            self.assertNotIn("readelf", source)


if __name__ == "__main__":
    unittest.main()
