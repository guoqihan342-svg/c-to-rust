from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from validation.tools.record_layout_evidence import validate_record_layout_evidence


class RecordLayoutEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = {
            "build_profile": {
                "target": {
                    "triple_or_abi": "x86_64-unknown-linux-gnu",
                    "endianness": "little",
                    "int_width": 32,
                    "long_width": 64,
                    "pointer_width": 64,
                }
            }
        }
        self.context = {
            "compile_database": {"sha256": "d" * 64},
            "target_abi": {
                "triple": "x86_64-unknown-linux-gnu",
                "endianness": "little",
                "pointer_width": 64,
            },
        }
        self.evidence = {
            "status": "captured",
            "dump_sha256": "a" * 64,
            "diagnostics_sha256": "b" * 64,
            "compile_arguments_sha256": "c" * 64,
            "compile_database_sha256": "d" * 64,
            "target_abi": self._target(),
            "arguments": [
                "-Xclang",
                "-fdump-record-layouts-complete",
                "-fsyntax-only",
                "unit.c",
            ],
            "used_layouts": [],
            "ambiguous_records": [],
            "error": None,
        }
        self.evidence["used_layouts"] = [
            {
                "record_type": "struct unit",
                "size_bytes": 16,
                "align_bytes": 8,
                "dump_sha256": "a" * 64,
                "diagnostics_sha256": "b" * 64,
                "compile_arguments_sha256": "c" * 64,
                "compile_database_sha256": "d" * 64,
                "target_abi": self._target(),
            }
        ]

    def test_accepts_consistent_hash_bound_layout(self) -> None:
        self._validate(self.evidence)

    def test_rejects_compile_database_drift(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["compile_database_sha256"] = "e" * 64
        with self.assertRaisesRegex(SystemExit, "compile_database_sha256 drifted"):
            self._validate(evidence)

    def test_rejects_target_conflict(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["target_abi"]["pointer_width"] = 32
        evidence["used_layouts"][0]["target_abi"]["pointer_width"] = 32
        with self.assertRaisesRegex(SystemExit, "conflicts with slice spec"):
            self._validate(evidence)

    def test_rejects_per_layout_hash_drift(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["used_layouts"][0]["dump_sha256"] = "f" * 64
        with self.assertRaisesRegex(SystemExit, "dump_sha256 drifted"):
            self._validate(evidence)

    def test_rejects_duplicate_or_ambiguous_consumption(self) -> None:
        duplicate = copy.deepcopy(self.evidence)
        duplicate["used_layouts"].append(copy.deepcopy(duplicate["used_layouts"][0]))
        with self.assertRaisesRegex(SystemExit, "duplicate record"):
            self._validate(duplicate)

        ambiguous = copy.deepcopy(self.evidence)
        ambiguous["ambiguous_records"] = ["struct unit"]
        with self.assertRaisesRegex(SystemExit, "also marked ambiguous"):
            self._validate(ambiguous)

    def test_accepts_strict_unavailable_shape(self) -> None:
        unavailable = {
            "status": "unavailable",
            "dump_sha256": None,
            "diagnostics_sha256": None,
            "compile_arguments_sha256": None,
            "compile_database_sha256": None,
            "target_abi": None,
            "arguments": [],
            "used_layouts": [],
            "ambiguous_records": [],
            "error": "clang_record_layout_dump_failed: unavailable",
        }
        self._validate(unavailable)

    def _validate(self, evidence: dict) -> None:
        report = {"lowering_report": {"record_layout_evidence": evidence}}
        with patch(
            "validation.tools.record_layout_evidence.resolve_native_build_context",
            return_value=self.context,
        ):
            validate_record_layout_evidence(self.spec, report, ".")

    @staticmethod
    def _target() -> dict:
        return {
            "triple_or_abi": "x86_64-unknown-linux-gnu",
            "endianness": "little",
            "char_width": 8,
            "short_width": 16,
            "int_width": 32,
            "long_width": 64,
            "long_long_width": 64,
            "pointer_width": 64,
            "char_align": 8,
            "short_align": 16,
            "int_align": 32,
            "long_align": 64,
            "long_long_align": 64,
            "pointer_align": 64,
            "plain_char_signed": True,
        }


if __name__ == "__main__":
    unittest.main()
