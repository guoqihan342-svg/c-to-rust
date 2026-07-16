from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.candidate_semantic_backend_contract import (
    parse_scalar_function,
)
from validation.tools._project_migration_harness.candidate_semantic_integer_literals import (
    source_integer_magnitudes,
)
from validation.tools._project_migration_harness.candidate_semantic_stimuli import (
    HELD_OUT_CASE_COUNT, held_out_scalar_cases, stimulus_binding,
)


class CandidateSemanticStimuliTests(unittest.TestCase):
    def test_source_threshold_and_neighbors_enter_held_out_cases(self) -> None:
        source = """int scalar_probe(int value) {
            return value == 100000 ? 9 : value + 1;
        }"""
        function = parse_scalar_function("scalar_probe", source)

        cases = held_out_scalar_cases(function, b"a" * 32, source)

        self.assertIn((99_999,), cases)
        self.assertIn((100_000,), cases)
        self.assertIn((100_001,), cases)
        self.assertEqual(HELD_OUT_CASE_COUNT, len(cases))
        self.assertEqual(HELD_OUT_CASE_COUNT, len(set(cases)))

    def test_integer_literal_scan_ignores_comments_strings_and_floats(self) -> None:
        source = r'''int scalar_probe(int value) {
            /* 900001 */ const char *text = "800001";
            return value == 0x186A0u || value == 077 ? 1 : (int)1e3;
        }'''

        self.assertEqual((100_000, 63, 1), source_integer_magnitudes(source))

    def test_signed_extrema_require_explicit_wrapping_semantics(self) -> None:
        function = parse_scalar_function(
            "scalar_probe", "int scalar_probe(int value) { return value; }",
        )

        ordinary = held_out_scalar_cases(function, b"a" * 32)
        wrapping = held_out_scalar_cases(
            function, b"a" * 32, signed_wrapping=True,
        )

        self.assertNotIn((-(1 << 31),), ordinary)
        self.assertNotIn(((1 << 31) - 1,), ordinary)
        self.assertIn((-(1 << 31),), wrapping)
        self.assertIn(((1 << 31) - 1,), wrapping)

    def test_macro_extrema_do_not_reintroduce_signed_overflow_ub_cases(self) -> None:
        function = parse_scalar_function(
            "scalar_probe", "int scalar_probe(int value) { return value + 1; }",
        )
        magnitude = (1 << 31) - 1

        ordinary = held_out_scalar_cases(
            function, b"a" * 32, macro_magnitudes=(magnitude,),
        )
        wrapping = held_out_scalar_cases(
            function, b"a" * 32, macro_magnitudes=(magnitude,),
            signed_wrapping=True,
        )

        self.assertNotIn((-(1 << 31),), ordinary)
        self.assertNotIn(((1 << 31) - 1,), ordinary)
        self.assertIn((-(1 << 31),), wrapping)
        self.assertIn(((1 << 31) - 1,), wrapping)

    def test_stimulus_receipt_content_binds_integer_macro_evidence(self) -> None:
        macro_binding = {"schema_version": 1, "status": "ready"}
        macro_binding["binding_sha256"] = content_sha256(macro_binding)

        receipt = stimulus_binding(
            b"a" * 32, ((100_000,),),
            integer_macro_binding=macro_binding,
        )

        self.assertEqual(macro_binding, receipt["integer_macro_binding"])
        self.assertEqual(
            content_sha256(macro_binding),
            receipt["integer_macro_binding_sha256"],
        )
        with self.assertRaisesRegex(ValueError, "binding drifted"):
            stimulus_binding(
                b"a" * 32, ((100_000,),),
                integer_macro_binding={**macro_binding, "status": "blocked"},
            )


if __name__ == "__main__":
    unittest.main()
