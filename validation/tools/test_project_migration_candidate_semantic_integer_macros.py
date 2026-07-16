from __future__ import annotations

import hashlib
import unittest

from validation.tools._project_migration_harness.c_index_macros import (
    source_macro_definitions,
)
from validation.tools._project_migration_harness.candidate_semantic_backend_contract import (
    parse_scalar_function,
)
from validation.tools._project_migration_harness.candidate_semantic_integer_macros import (
    MAX_MACRO_DEFINITIONS,
    MAX_MACRO_TOTAL_SOURCE_BYTES,
    collect_integer_macro_boundaries,
)
from validation.tools._project_migration_harness.candidate_semantic_stimuli import (
    held_out_scalar_cases,
)


class CandidateSemanticIntegerMacroTests(unittest.TestCase):
    def test_literal_symbol_parentheses_and_unary_feed_boundary_cases(self) -> None:
        source = """#define BASE_LIMIT 100000
#define ACTIVE_LIMIT (-(+BASE_LIMIT))
int scalar_probe(int value) {
    return value < ACTIVE_LIMIT ? 1 : 0;
}
"""
        boundaries = self._collect(source, cindex_names=("ACTIVE_LIMIT",))
        function = parse_scalar_function(
            "scalar_probe", source[source.index("int scalar_probe"):],
        )

        cases = held_out_scalar_cases(
            function, b"m" * 32, macro_magnitudes=boundaries.magnitudes,
        )

        self.assertEqual((100_000,), boundaries.magnitudes)
        self.assertIn((-100_001,), cases)
        self.assertIn((-100_000,), cases)
        self.assertIn((-99_999,), cases)
        self.assertEqual("ready", boundaries.binding["status"])
        self.assertEqual(1, boundaries.binding["accepted_magnitude_count"])

    def test_compile_fact_definitions_resolve_dependencies(self) -> None:
        source = """int scalar_probe(int value) {
    return value == ACTIVE_LIMIT ? 1 : 0;
}
"""
        boundaries = self._collect(
            source,
            compile_arguments=("-std=c11", "-DBASE_LIMIT=4096", "-DACTIVE_LIMIT=(+BASE_LIMIT)"),
        )

        self.assertEqual((4096,), boundaries.magnitudes)
        self.assertEqual("ready", boundaries.binding["status"])

    def test_unconditional_bound_header_macro_is_eligible(self) -> None:
        source = """#include "limits.h"
int scalar_probe(int value) { return value >= HEADER_LIMIT; }
"""
        header = b"#define HEADER_BASE 8192\n#define HEADER_LIMIT (HEADER_BASE)\n"

        boundaries = self._collect(
            source, header_sources=(("limits.h", header),),
        )

        self.assertEqual((8192,), boundaries.magnitudes)

    def test_function_like_quotes_characters_floats_and_comment_values_are_excluded(self) -> None:
        source = r'''#define APPLY(x) (x)
#define TEXT_VALUE "900001"
#define CHAR_VALUE 'A'
#define FLOAT_VALUE 1e3
#define COMMENT_VALUE /* 700001 */
#define COMPLEX_VALUE (100 + 1)
int scalar_probe(int value) {
    return value + APPLY(value) + TEXT_VALUE + CHAR_VALUE
        + FLOAT_VALUE + COMMENT_VALUE + COMPLEX_VALUE;
}
'''

        boundaries = self._collect(source)

        self.assertEqual((), boundaries.magnitudes)
        self.assertEqual("ready_with_ignored", boundaries.binding["status"])
        blockers = boundaries.binding["blocker_counts"]
        self.assertEqual(1, blockers["function_like"])
        self.assertEqual(5, blockers["expression_unsupported"])

    def test_unsigned_dependency_cannot_be_negated_as_a_math_integer(self) -> None:
        source = """#define UNSIGNED_LIMIT 1U
#define NEGATIVE_LIMIT (-UNSIGNED_LIMIT)
int scalar_probe(int value) { return value == NEGATIVE_LIMIT; }
"""

        boundaries = self._collect(source)

        self.assertEqual((), boundaries.magnitudes)
        self.assertEqual(
            1, boundaries.binding["blocker_counts"]["unsafe_unsigned_unary_minus"],
        )

    def test_dependency_cycle_is_fail_closed_and_deterministic(self) -> None:
        source = """#define FIRST_LIMIT SECOND_LIMIT
#define SECOND_LIMIT FIRST_LIMIT
int scalar_probe(int value) { return value == FIRST_LIMIT; }
"""

        first = self._collect(source)
        second = self._collect(source)

        self.assertEqual((), first.magnitudes)
        self.assertEqual(1, first.binding["blocker_counts"]["dependency_cycle"])
        self.assertEqual(first.binding, second.binding)

    def test_redefinition_is_fail_closed_even_when_replacements_match(self) -> None:
        source = """#define ACTIVE_LIMIT 12345
#define ACTIVE_LIMIT 12345
int scalar_probe(int value) { return value == ACTIVE_LIMIT; }
"""

        boundaries = self._collect(source)

        self.assertEqual((), boundaries.magnitudes)
        self.assertEqual(1, boundaries.binding["blocker_counts"]["redefined"])

    def test_conditional_definition_is_not_used_as_a_threshold(self) -> None:
        source = """#if FEATURE_ENABLED
#define ACTIVE_LIMIT 12345
#endif
int scalar_probe(int value) { return value == ACTIVE_LIMIT; }
"""

        boundaries = self._collect(source)

        self.assertEqual((), boundaries.magnitudes)
        self.assertEqual(
            1, boundaries.binding["blocker_counts"]["conditional_definition"],
        )

    def test_source_size_budget_blocks_macro_slice_without_partial_values(self) -> None:
        prefix = b"/*" + b"x" * MAX_MACRO_TOTAL_SOURCE_BYTES + b"*/\n"
        function = b"int scalar_probe(int value) { return value == LIMIT; }\n"
        source = prefix + function

        boundaries = collect_integer_macro_boundaries(
            function_source=function,
            source_path="unit.c",
            source_bytes=source,
            function_byte_start=len(prefix),
            node_id="node", unit_id="unit",
        )

        self.assertEqual((), boundaries.magnitudes)
        self.assertEqual("blocked", boundaries.binding["status"])
        self.assertEqual(
            1, boundaries.binding["blocker_counts"]["source_budget_exceeded"],
        )

    def test_definition_count_budget_blocks_macro_slice(self) -> None:
        definitions = "".join(
            f"#define LIMIT_{index} {index}\n"
            for index in range(MAX_MACRO_DEFINITIONS + 1)
        )
        source = definitions + "int scalar_probe(int value) { return value == LIMIT_0; }\n"

        boundaries = self._collect(source)

        self.assertEqual((), boundaries.magnitudes)
        self.assertEqual("blocked", boundaries.binding["status"])
        self.assertEqual(
            1, boundaries.binding["blocker_counts"]["definition_budget_exceeded"],
        )

    def test_compile_definitions_share_the_definition_budget(self) -> None:
        source = "int scalar_probe(int value) { return value == LIMIT_0; }\n"
        arguments = tuple(
            f"-DLIMIT_{index}={index}"
            for index in range(MAX_MACRO_DEFINITIONS + 1)
        )

        boundaries = self._collect(source, compile_arguments=arguments)

        self.assertEqual((), boundaries.magnitudes)
        self.assertEqual("blocked", boundaries.binding["status"])
        self.assertEqual(
            1, boundaries.binding["blocker_counts"]["definition_budget_exceeded"],
        )

    def test_unrelated_definition_count_does_not_expand_resolution_work(self) -> None:
        definitions = "".join(
            f"#define UNUSED_{index} {index}\n" for index in range(200)
        )
        source = definitions + (
            "#define ACTIVE_LIMIT 65535\n"
            "int scalar_probe(int value) { return value == ACTIVE_LIMIT; }\n"
        )

        boundaries = self._collect(source)

        self.assertEqual((65535,), boundaries.magnitudes)
        self.assertEqual("ready", boundaries.binding["status"])

    def test_cindex_macro_fact_must_match_bound_directive(self) -> None:
        source = """#define ACTIVE_LIMIT 12345
int scalar_probe(int value) { return value == ACTIVE_LIMIT; }
"""
        facts = list(self._cindex_facts(source, ("ACTIVE_LIMIT",)))
        facts[0] = {**facts[0], "directive_sha256": "0" * 64}

        with self.assertRaisesRegex(ValueError, "not source bound"):
            self._collect(source, cindex_facts=tuple(facts))

    def test_function_slice_must_match_bound_source_bytes(self) -> None:
        source = b"int scalar_probe(int value) { return value == LIMIT; }\n"

        with self.assertRaisesRegex(ValueError, "function source is not source bound"):
            collect_integer_macro_boundaries(
                function_source=source.replace(b"LIMIT", b"OTHER"),
                source_path="unit.c", source_bytes=source,
                function_byte_start=0, node_id="node", unit_id="unit",
            )

    def test_content_change_changes_macro_binding(self) -> None:
        first = self._collect(
            "#define LIMIT 10000\nint scalar_probe(int value) { return value == LIMIT; }\n",
        )
        second = self._collect(
            "#define LIMIT 10001\nint scalar_probe(int value) { return value == LIMIT; }\n",
        )

        self.assertNotEqual(
            first.binding["binding_sha256"], second.binding["binding_sha256"],
        )
        self.assertNotEqual(first.magnitudes, second.magnitudes)

    def _collect(
        self, source: str, *, cindex_names: tuple[str, ...] = (),
        cindex_facts: tuple[dict, ...] | None = None,
        header_sources: tuple[tuple[str, bytes], ...] = (),
        compile_arguments: tuple[str, ...] = (),
    ):
        raw = source.encode("utf-8")
        start = source.index("int scalar_probe")
        facts = (
            self._cindex_facts(source, cindex_names)
            if cindex_facts is None else cindex_facts
        )
        return collect_integer_macro_boundaries(
            function_source=raw[start:], source_path="unit.c", source_bytes=raw,
            function_byte_start=start, node_id="node", unit_id="unit",
            header_sources=header_sources, cindex_macro_facts=facts,
            compile_arguments=compile_arguments,
        )

    @staticmethod
    def _cindex_facts(source: str, names: tuple[str, ...]) -> tuple[dict, ...]:
        raw = source.encode("utf-8")
        source_sha = hashlib.sha256(raw).hexdigest()
        definitions = source_macro_definitions({
            "raw": raw, "path": "unit.c", "sha256": source_sha,
        })
        return tuple({
            "node_id": "node", "unit_id": "unit", **definition,
        } for definition in definitions if definition["name"] in names)


if __name__ == "__main__":
    unittest.main()
