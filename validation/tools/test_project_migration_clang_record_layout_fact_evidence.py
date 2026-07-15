from __future__ import annotations

import unittest

from validation.tools._project_migration_harness import (
    clang_record_layout_fact_evidence as layout_evidence,
)
from validation.tools._project_migration_harness.clang_record_layout_fact_evidence import (
    ClangRecordLayoutFactEvidenceError,
    MAX_CLANG_RECORD_LAYOUT_EVIDENCE_BYTES,
    MAX_CLANG_RECORD_LAYOUT_LINE_BYTES,
    MAX_CLANG_RECORD_LAYOUT_RECORDS,
    parse_clang_record_layout_fact_evidence,
    validate_clang_record_layout_fact_evidence,
)


TOOLCHAIN_SHA256 = "a" * 64
TARGET_CONTEXT_SHA256 = "b" * 64


class ProjectMigrationClangRecordLayoutFactEvidenceTests(unittest.TestCase):
    def test_normalizes_named_struct_fields_and_keeps_claims_closed(self) -> None:
        raw = _layout(
            "struct Packet",
            (0, "unsigned int sequence"),
            (4, "unsigned char tag[4]"),
            size=8,
            align=4,
        )

        result = _parse(raw)

        self.assertEqual("facts-ready", result["status"])
        self.assertEqual(1, result["record_count"])
        self.assertEqual({
            "name": "Packet",
            "kind": "struct",
            "size_bits": 64,
            "align_bits": 32,
            "fields": [
                {"ordinal": 0, "name": "sequence", "type_text": "unsigned int",
                 "offset_bits": 0},
                {"ordinal": 1, "name": "tag", "type_text": "unsigned char[4]",
                 "offset_bits": 32},
            ],
        }, result["records"][0])
        self.assertEqual(
            {"semantic_gate": False, "translation_coverage_numerator": 0},
            result["claim_boundary"],
        )
        self.assertNotIn("interface_closure", result)
        self.assertEqual(result, _parse(raw))
        from_stderr = parse_clang_record_layout_fact_evidence(
            b"bounded diagnostic\n", raw, TOOLCHAIN_SHA256, TARGET_CONTEXT_SHA256,
        )
        self.assertEqual(result["records"], from_stderr["records"])
        self.assertNotEqual(result["raw_sha256"], from_stderr["raw_sha256"])

    def test_union_is_normalized_but_remains_blocked(self) -> None:
        result = _parse(_layout(
            "union Value", (0, "unsigned int integer"), (0, "float decimal"),
            size=4, align=4,
        ))

        self.assertEqual("blocked", result["status"])
        self.assertEqual("union", result["records"][0]["kind"])
        self.assertIn(
            "clang_record_layout_union_unsupported", _blocker_codes(result),
        )

    def test_blocks_bitfield_flexible_array_and_anonymous_constructs(self) -> None:
        cases = {
            "bitfield": (
                _raw_block("struct Flags", ["     0:0-2 |   unsigned int mode"]),
                "clang_record_layout_bitfield_unsupported",
            ),
            "flexible": (
                _layout("struct Buffer", (0, "unsigned int length"),
                        (4, "unsigned char data[]"), size=4, align=4),
                "clang_record_layout_flexible_array_unsupported",
            ),
            "anonymous-record": (
                _layout("struct (anonymous at input.c:1:1)",
                        (0, "int value"), size=4, align=4),
                "clang_record_layout_anonymous_record",
            ),
            "anonymous-field": (
                _layout("struct Outer", (0, "struct Inner"), size=4, align=4),
                "clang_record_layout_anonymous_field",
            ),
        }
        for label, (raw, code) in cases.items():
            with self.subTest(label=label):
                result = _parse(raw)
                self.assertEqual("blocked", result["status"])
                self.assertIn(code, _blocker_codes(result))

    def test_blocks_duplicate_unparseable_incomplete_and_out_of_bounds_layouts(self) -> None:
        valid = _layout("struct Item", (0, "int value"), size=4, align=4)
        cases = {
            "duplicate": (
                valid + valid, "clang_record_layout_duplicate_record",
            ),
            "unparseable": (
                _layout("struct Callback", (0, "int (*callback)(int)"),
                        size=8, align=8),
                "clang_record_layout_field_unparseable",
            ),
            "missing-align": (
                _raw_block("struct Item", ["         0 |   int value"],
                           summary="sizeof=4"),
                "clang_record_layout_size_align_missing",
            ),
            "out-of-bounds": (
                _layout("struct Item", (4, "int value"), size=4, align=4),
                "clang_record_layout_field_offset_out_of_bounds",
            ),
        }
        for label, (raw, code) in cases.items():
            with self.subTest(label=label):
                result = _parse(raw)
                self.assertEqual("blocked", result["status"])
                self.assertIn(code, _blocker_codes(result))

    def test_rejects_bad_utf8_and_input_floods(self) -> None:
        floods = {
            "bad-utf8": b"\xff",
            "total-size": b"x" * (MAX_CLANG_RECORD_LAYOUT_EVIDENCE_BYTES + 1),
            "line-size": b"x" * (MAX_CLANG_RECORD_LAYOUT_LINE_BYTES + 1),
            "record-count": ((_MARKER + "\n") *
                             (MAX_CLANG_RECORD_LAYOUT_RECORDS + 1)).encode("ascii"),
        }
        for label, raw in floods.items():
            with self.subTest(label=label):
                with self.assertRaises(ClangRecordLayoutFactEvidenceError):
                    _parse(raw)

    def test_reparse_validation_detects_raw_toolchain_target_and_fact_drift(self) -> None:
        raw = _layout("struct Item", (0, "int value"), size=4, align=4)
        result = _parse(raw)
        self.assertEqual(
            result,
            validate_clang_record_layout_fact_evidence(
                result, raw, b"", TOOLCHAIN_SHA256, TARGET_CONTEXT_SHA256,
            ),
        )

        drifts = {
            "raw": (raw + b"bounded diagnostic\n", b"", TOOLCHAIN_SHA256,
                    TARGET_CONTEXT_SHA256),
            "toolchain": (raw, b"", "c" * 64, TARGET_CONTEXT_SHA256),
            "target": (raw, b"", TOOLCHAIN_SHA256, "d" * 64),
        }
        for label, arguments in drifts.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    ClangRecordLayoutFactEvidenceError, "source_reparse_drift",
                ):
                    validate_clang_record_layout_fact_evidence(result, *arguments)

        forged = dict(result)
        forged["facts_sha256"] = "f" * 64
        with self.assertRaisesRegex(
            ClangRecordLayoutFactEvidenceError, "source_reparse_drift",
        ):
            validate_clang_record_layout_fact_evidence(
                forged, raw, b"", TOOLCHAIN_SHA256, TARGET_CONTEXT_SHA256,
            )

    def test_same_dimensions_with_different_offsets_change_facts_hash(self) -> None:
        first = _parse(_layout(
            "struct Pair", (0, "int left"), (4, "int right"), size=8, align=4,
        ))
        second = _parse(_layout(
            "struct Pair", (0, "int left"), (0, "int right"), size=8, align=4,
        ))

        self.assertEqual(first["records"][0]["size_bits"],
                         second["records"][0]["size_bits"])
        self.assertNotEqual(first["records"][0]["fields"],
                            second["records"][0]["fields"])
        self.assertNotEqual(first["facts_sha256"], second["facts_sha256"])

    def test_production_module_stays_within_line_budget(self) -> None:
        source = layout_evidence.__file__
        self.assertIsNotNone(source)
        with open(source, encoding="utf-8") as handle:
            self.assertLessEqual(sum(1 for _ in handle), 300)


_MARKER = "*** Dumping AST Record Layout"


def _parse(stdout: bytes) -> dict:
    return parse_clang_record_layout_fact_evidence(
        stdout, b"", TOOLCHAIN_SHA256, TARGET_CONTEXT_SHA256,
    )


def _layout(record: str, *fields: tuple[int, str], size: int, align: int) -> bytes:
    rows = [f"{offset:10d} |   {field}" for offset, field in fields]
    return _raw_block(record, rows, summary=f"sizeof={size}, align={align}")


def _raw_block(
    record: str, rows: list[str], summary: str = "sizeof=4, align=4",
) -> bytes:
    lines = [_MARKER, f"         0 | {record}", *rows, f"           | [{summary}]"]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _blocker_codes(value: dict) -> set[str]:
    return {item["code"] for item in value["blockers"]}


if __name__ == "__main__":
    unittest.main()
