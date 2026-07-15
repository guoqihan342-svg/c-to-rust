from __future__ import annotations

import copy
import hashlib
import json
import unittest

from validation.tools._project_migration_harness.clang_record_layout_fact_evidence import (
    ClangRecordLayoutFactEvidenceError,
)
from validation.tools._project_migration_harness.clang_record_layout_selection import (
    parse_selected_clang_record_layout_fact_evidence,
    validate_selected_clang_record_layout_fact_evidence,
)


TOOLCHAIN = "a" * 64
TARGET = "b" * 64
MARKER = "*** Dumping AST Record Layout"


class ProjectMigrationClangRecordLayoutSelectionTests(unittest.TestCase):
    def test_system_layout_noise_is_excluded_from_source_bound_records(self) -> None:
        raw = b"".join((
            _layout("__NSConstantString_tag", "int flags"),
            _layout("Packet", "unsigned int sequence"),
            _layout("__va_list_tag", "void *overflow_arg_area"),
        ))
        result = _parse(raw, _interface(("Packet", True)))
        self.assertEqual("facts-ready", result["status"])
        self.assertEqual(["Packet"], [item["name"] for item in result["records"]])
        self.assertEqual([], result["blockers"])
        self.assertFalse(result["section_closure"])

    def test_unselected_unsupported_layout_does_not_poison_selection(self) -> None:
        system_union = _raw_block("union SystemChoice", ["         0 |   int value"])
        raw = system_union + _layout("Packet", "int value")
        result = _parse(raw, _interface(("Packet", True)))
        self.assertEqual("facts-ready", result["status"])
        self.assertEqual(["Packet"], [item["name"] for item in result["records"]])

    def test_missing_incomplete_duplicate_and_empty_selection_block(self) -> None:
        cases = {
            "missing": (
                _layout("Other", "int value"), _interface(("Packet", True)),
                "clang_record_layout_selected_record_missing",
            ),
            "incomplete": (
                _layout("Packet", "int value"), _interface(("Packet", False)),
                "clang_record_layout_selected_record_incomplete",
            ),
            "duplicate-layout": (
                _layout("Packet", "int value") * 2, _interface(("Packet", True)),
                "clang_record_layout_duplicate_record",
            ),
            "empty": (
                _layout("System", "int value"), _interface(),
                "clang_record_layout_selected_record_set_empty",
            ),
        }
        for label, (raw, interface, code) in cases.items():
            with self.subTest(label=label):
                result = _parse(raw, interface)
                self.assertEqual("blocked", result["status"])
                self.assertIn(code, _codes(result))

    def test_selection_and_raw_streams_are_recomputed(self) -> None:
        raw = _layout("Packet", "int value")
        interface = _interface(("Packet", True))
        result = _parse(raw, interface)
        self.assertEqual(
            result,
            validate_selected_clang_record_layout_fact_evidence(
                result, raw, b"", TOOLCHAIN, TARGET, interface,
            ),
        )
        changed = _interface(("Other", True))
        with self.assertRaisesRegex(
            ClangRecordLayoutFactEvidenceError, "selected_source_reparse_drift",
        ):
            validate_selected_clang_record_layout_fact_evidence(
                result, raw, b"", TOOLCHAIN, TARGET, changed,
            )
        forged = copy.deepcopy(interface)
        forged["records"][0]["complete"] = False
        with self.assertRaisesRegex(
            ClangRecordLayoutFactEvidenceError, "interface_evidence_invalid",
        ):
            _parse(raw, forged)


def _parse(raw: bytes, interface: dict) -> dict:
    return parse_selected_clang_record_layout_fact_evidence(
        raw, b"", TOOLCHAIN, TARGET, interface,
    )


def _interface(*records: tuple[str, bool]) -> dict:
    value = {
        "schema_version": 1,
        "status": "parsed",
        "parser": "clang_ast_top_level_interface_v1",
        "limits": {"max_bytes": 1, "max_nodes": 1, "max_depth": 1},
        "input_bindings": {},
        "functions": [],
        "globals": [],
        "records": [{
            "name": name,
            "tag": "struct",
            "complete": complete,
            "fields": [],
            "source_spans": [{
                "path": "src/input.c", "sha256": "c" * 64,
                "byte_start": 0, "byte_end": 1,
            }],
        } for name, complete in records],
        "initialization_facts": [],
        "blockers": [],
        "section_closure": False,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    compact = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("ascii")
    value["evidence_sha256"] = hashlib.sha256(compact).hexdigest()
    return value


def _layout(name: str, field: str) -> bytes:
    return _raw_block(f"struct {name}", [f"         0 |   {field}"])


def _raw_block(record: str, rows: list[str]) -> bytes:
    lines = [
        MARKER, f"         0 | {record}", *rows,
        "           | [sizeof=8, align=8]",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _codes(value: dict) -> set[str]:
    return {item["code"] for item in value["blockers"]}


if __name__ == "__main__":
    unittest.main()
