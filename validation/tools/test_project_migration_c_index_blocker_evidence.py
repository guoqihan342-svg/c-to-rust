from __future__ import annotations

from copy import deepcopy
from typing import Any
import unittest

from validation.tools._project_migration_harness.c_index_blocker_validation import (
    CIndexBlockerValidationError,
    validate_blocker_catalog,
)
from validation.tools._project_migration_harness.c_index_blockers import (
    build_blocker_catalog,
)


SOURCE_SHA = "a" * 64
DIRECTIVE_SHA = "b" * 64


def blocker(
    source_path: str,
    *,
    unit_id: str = "unit-1",
    kind: str = "header_conditional_preprocessor",
    byte_offset: int = 7,
) -> dict[str, Any]:
    return {
        "unit_id": unit_id,
        "kind": kind,
        "byte_offset": byte_offset,
        "source_path": source_path,
        "source_sha256": SOURCE_SHA,
        "directive_sha256": DIRECTIVE_SHA,
    }


def catalog() -> dict[str, Any]:
    return build_blocker_catalog([
        blocker("include/left.h"),
        blocker("include/right.h"),
    ])


class CIndexBlockerEvidenceTests(unittest.TestCase):
    def test_same_offset_in_distinct_headers_preserves_provenance(self) -> None:
        raw = [blocker("include/left.h"), blocker("include/right.h")]
        value = build_blocker_catalog(raw)
        before = deepcopy(value)

        validate_blocker_catalog(value)

        self.assertEqual(before, value)
        self.assertEqual(value, build_blocker_catalog(list(reversed(raw))))
        self.assertEqual(2, len(value["blocker_evidence_facts"]))
        self.assertEqual(2, value["blockers"][0]["occurrence_count"])
        paths = {
            fact["source_path"]
            for fact in value["blocker_evidence_facts"].values()
        }
        self.assertEqual({"include/left.h", "include/right.h"}, paths)

    def test_rejects_tampered_fact_sha_binding(self) -> None:
        value = catalog()
        digest = next(iter(value["blocker_evidence_facts"]))
        value["blocker_evidence_facts"][digest]["source_path"] = "include/other.h"

        self.assert_invalid(value, "fact_sha256_mismatch")

    def test_rejects_tampered_set_sha_and_count(self) -> None:
        for mutation, error in (
            ("sha", "set_sha256_mismatch"),
            ("count", "evidence_count_mismatch"),
        ):
            with self.subTest(mutation=mutation):
                value = catalog()
                digest = next(iter(value["blocker_evidence_sets"]))
                if mutation == "sha":
                    evidence_set = value["blocker_evidence_sets"].pop(digest)
                    replacement = "f" * 64
                    value["blocker_evidence_sets"][replacement] = evidence_set
                    value["blockers"][0]["evidence_set_sha256"] = replacement
                else:
                    value["blocker_evidence_sets"][digest]["evidence_count"] = 1
                self.assert_invalid(value, error)

    def test_rejects_dangling_set_and_fact_references(self) -> None:
        with self.subTest(reference="set"):
            value = catalog()
            value["blockers"][0]["evidence_set_sha256"] = "f" * 64
            self.assert_invalid(value, "dangling_blocker_evidence_set")

        with self.subTest(reference="fact"):
            value = catalog()
            digest = next(iter(value["blocker_evidence_facts"]))
            del value["blocker_evidence_facts"][digest]
            self.assert_invalid(value, "dangling_blocker_evidence_fact")

    def test_rejects_unreferenced_fact_and_set(self) -> None:
        extra = build_blocker_catalog([
            blocker("include/extra.h", unit_id="unit-2", kind="dynamic_include")
        ])
        with self.subTest(evidence="fact"):
            value = catalog()
            value["blocker_evidence_facts"].update(extra["blocker_evidence_facts"])
            self.assert_invalid(value, "unreferenced_blocker_evidence_fact")

        with self.subTest(evidence="set"):
            value = catalog()
            value["blocker_evidence_facts"].update(extra["blocker_evidence_facts"])
            value["blocker_evidence_sets"].update(extra["blocker_evidence_sets"])
            self.assert_invalid(value, "unreferenced_blocker_evidence_set")

    def test_rejects_duplicate_evidence_and_blocker_identity(self) -> None:
        with self.subTest(duplicate="evidence_ref"):
            value = catalog()
            evidence_set = next(iter(value["blocker_evidence_sets"].values()))
            evidence_set["evidence_refs"].append(evidence_set["evidence_refs"][0])
            evidence_set["evidence_count"] += 1
            self.assert_invalid(value, "duplicate_blocker_evidence_ref")

        with self.subTest(duplicate="blocker"):
            value = catalog()
            value["blockers"].append(deepcopy(value["blockers"][0]))
            self.assert_invalid(value, "duplicate_blocker_identity")

    def test_rejects_tampered_blocker_summary(self) -> None:
        for field, value, error in (
            ("occurrence_count", 1, "blocker_occurrence_count_mismatch"),
            ("byte_offset", 8, "blocker_byte_offset_mismatch"),
        ):
            with self.subTest(field=field):
                tampered = catalog()
                tampered["blockers"][0][field] = value
                self.assert_invalid(tampered, error)

    def assert_invalid(self, value: Any, error: str) -> None:
        with self.assertRaisesRegex(CIndexBlockerValidationError, error):
            validate_blocker_catalog(value)


if __name__ == "__main__":
    unittest.main()
