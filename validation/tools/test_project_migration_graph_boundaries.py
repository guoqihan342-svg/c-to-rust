from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.c_index import index_translation_units
from validation.tools._project_migration_harness.context_pages import build_context_pages
from validation.tools._project_migration_harness.context_index_store import (
    prepare_context_indexes,
)
from validation.tools._project_migration_harness.migration_graph import build_migration_graph


class ProjectMigrationGraphBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="project-graph-boundary-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_compile_variants_have_distinct_content_bound_node_ids(self) -> None:
        first = self.unit("src/unit.c", "int unit(void) { return 1; }\n", "variant-a")
        second = {**first, "unit_id": "variant-b"}

        index = index_translation_units(self.root, [first, second])

        self.assertEqual(2, len(index["nodes"]))
        self.assertEqual(2, len({item["node_id"] for item in index["nodes"]}))
        graph = build_migration_graph(index)
        self.assertTrue(graph["sccs"])
        self.assertTrue(
            all(item["classification"] == "boundary_required" for item in graph["sccs"])
        )
        self.assertTrue(
            all(
                "ambiguous_external_definition" in item["structural_reasons"]
                for item in graph["sccs"]
            )
        )

    def test_shared_global_users_form_one_context_group(self) -> None:
        unit = self.unit(
            "state.c",
            "static int counter[4];\n"
            "int read_counter(void) { return counter[0]; }\n"
            "void write_counter(int value) { counter[0] = value; }\n",
            "state-variant",
        )

        graph = build_migration_graph(index_translation_units(self.root, [unit]))

        self.assertEqual(1, len(graph["sccs"]))
        self.assertEqual("context_group", graph["sccs"][0]["classification"])
        self.assertIn("shared_global_state", graph["sccs"][0]["structural_reasons"])
        self.assertEqual(1, len(graph["shared_state_edges"]))

    def test_conditional_preprocessor_and_used_function_macro_fail_closed(self) -> None:
        unit = self.unit(
            "conditional.c",
            "#define APPLY(x) ((x) + 1)\n"
            "#if FEATURE\nint selected(void) { return APPLY(1); }\n#endif\n",
            "conditional-variant",
        )

        index = index_translation_units(self.root, [unit])

        self.assertEqual("ready_with_boundaries", index["status"])
        kinds = {item["kind"] for item in index["parser"]["blockers"]}
        self.assertIn("conditional_preprocessor_unsupported", kinds)
        self.assertIn("function_like_macro_call_unsupported", kinds)
        self.assertEqual(1, len(index["nodes"]))
        self.assertEqual("function", index["nodes"][0]["node_kind"])
        self.assertIn("int selected", index["nodes"][0]["source"]["content"])
        graph = build_migration_graph(index)
        self.assertEqual("ready_with_boundaries", graph["status"])
        contexts = build_context_pages(
            index, graph, max_page_bytes=4_096, max_page_tokens=4_096
        )
        self.assertEqual("ready_with_boundaries", contexts["status"])
        self.assertTrue(
            any(fact["kind"] == "parser_boundary" for fact in contexts["shared_facts"].values())
        )

    def test_array_global_uses_declarator_name_not_bound_expression(self) -> None:
        unit = self.unit(
            "array.c",
            "enum { COUNT = 4 };\nint table[COUNT];\n"
            "int first(void) { return table[0]; }\n",
            "array-variant",
        )

        index = index_translation_units(self.root, [unit])

        self.assertIn("table", {item["symbol"] for item in index["globals"]})
        self.assertNotIn("COUNT", {item["symbol"] for item in index["globals"]})

    def test_unconditional_global_and_referenced_macro_survive_unrelated_boundaries(self) -> None:
        unit = self.unit(
            "macro-global.c",
            "#define FIELD(object) ((object)->value)\n"
            "static const int table[] = { 3, 5 };\n"
            "#if FEATURE\nstatic int conditional_state = 9;\n#endif\n"
            "struct record { int value; };\n"
            "int read_record(struct record *item) {\n"
            "  return FIELD(item) + table[0];\n"
            "}\n",
            "macro-global-variant",
        )

        index = index_translation_units(self.root, [unit])

        globals_by_name = {item["symbol"]: item for item in index["globals"]}
        self.assertIn("table", globals_by_name)
        self.assertNotIn("conditional_state", globals_by_name)
        node = next(item for item in index["nodes"] if item["symbol"] == "read_record")
        self.assertEqual(["FIELD"], [
            item["name"] for item in node["macro_definitions"]
        ])
        pages = build_context_pages(index, build_migration_graph(index))
        definitions = [
            fact["payload"] for fact in pages["shared_facts"].values()
            if fact["kind"] == "source_macro_definition"
        ]
        self.assertEqual("((object)->value)", definitions[0]["replacement"])
        self.assertEqual("unconditional", definitions[0]["activation_status"])

    def test_local_include_and_global_initializer_are_model_context(self) -> None:
        self.unit("src/config.h", "#define INITIAL_VALUE 7\n", "header-only")
        unit = self.unit(
            "src/main.c",
            '#include "config.h"\n'
            "static int state = INITIAL_VALUE;\n"
            "int read_state(void) { return state; }\n",
            "main-variant",
        )

        index = index_translation_units(self.root, [unit])

        self.assertEqual("ready", index["status"])
        context = index["unit_contexts"][0]
        header = context["headers"][0]
        self.assertEqual("src/config.h", header["path"])
        self.assertIn(header["header_fact_sha256"], index["header_facts"])
        self.assertEqual("complete", context["top_level"]["coverage"]["status"])
        state = next(item for item in index["globals"] if item["symbol"] == "state")
        self.assertEqual("static int state = INITIAL_VALUE;", state["source"]["content"])
        graph = build_migration_graph(index)
        pages = build_context_pages(index, graph)
        kinds = {fact["kind"] for fact in pages["shared_facts"].values()}
        self.assertTrue({"header_source", "global_source", "translation_unit_coverage"} <= kinds)
        visible_kinds = {
            pages["shared_facts"][digest]["kind"]
            for page in pages["pages"] for digest in page["fact_refs"]
        }
        self.assertIn("header_source", visible_kinds)
        self.assertIn("context_retrieval_summary", visible_kinds)
        self.assertEqual(1, len(pages["retrieval_bindings"]))
        self.assertEqual("ready", pages["retrieval_bindings"][0]["selection_status"])

    def test_large_header_is_host_retrievable_without_flooding_seed_pages(self) -> None:
        header = "".join(
            f"#define VALUE_{index} ({index} + {index})\n" for index in range(800)
        )
        self.unit("src/large.h", header, "header-only")
        unit = self.unit(
            "src/main.c",
            '#include "large.h"\nint read_value(void) { return VALUE_799; }\n',
            "main-variant",
        )

        index = index_translation_units(self.root, [unit])
        pack = build_context_pages(
            index, build_migration_graph(index),
            max_page_bytes=4_096, max_page_tokens=4_096,
        )

        self.assertLessEqual(len(pack["pages"]), 4)
        self.assertTrue(pack["retrieval_sets"])
        omitted = sum(
            binding["omitted_fact_count"] for binding in pack["retrieval_bindings"]
        )
        self.assertGreater(omitted, 10)
        visible_content = "".join(
            str(pack["shared_facts"][digest]["payload"].get("content", ""))
            for page in pack["pages"] for digest in page["fact_refs"]
            if pack["shared_facts"][digest]["kind"] == "header_source"
        )
        self.assertIn("VALUE_799", visible_content)
        self.assertNotIn("VALUE_0", visible_content)
        prepare_context_indexes(pack, out_root_rel="target/run")
        first = next(iter(pack["retrieval_sets"].values()))
        first["fact_count"] += 1
        with self.assertRaisesRegex(ValueError, "set count"):
            prepare_context_indexes(pack, out_root_rel="target/run")

    def test_selection_receipt_tampering_is_rejected(self) -> None:
        self.unit("src/api.h", "#define API_VALUE 9\n", "header-only")
        unit = self.unit(
            "src/main.c",
            '#include "api.h"\nint read_api(void) { return API_VALUE; }\n',
            "main-variant",
        )
        index = index_translation_units(self.root, [unit])
        pack = build_context_pages(index, build_migration_graph(index))

        pack["retrieval_bindings"][0]["selection_receipt_sha256"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "binding does not match"):
            prepare_context_indexes(pack, out_root_rel="target/run")

    def test_unresolved_include_forces_whole_translation_unit_boundary(self) -> None:
        unit = self.unit(
            "src/main.c",
            "#include <missing_project_api.h>\nint entry(void) { return 1; }\n",
            "missing-include-variant",
        )

        index = index_translation_units(self.root, [unit])

        self.assertEqual("ready_with_boundaries", index["status"])
        self.assertIn(
            "include_dependency_unresolved",
            {item["kind"] for item in index["parser"]["blockers"]},
        )
        self.assertEqual("function", index["nodes"][0]["node_kind"])
        graph = build_migration_graph(index)
        self.assertEqual("boundary_required", graph["sccs"][0]["classification"])

    def test_fatal_lexical_damage_keeps_whole_translation_unit_boundary(self) -> None:
        unit = self.unit(
            "src/broken.c",
            "int visible(void) { return 1; }\n/* unterminated\n",
            "broken-variant",
        )

        index = index_translation_units(self.root, [unit])

        self.assertEqual(1, len(index["nodes"]))
        self.assertEqual("translation_unit_boundary", index["nodes"][0]["node_kind"])

    def test_shared_headers_are_content_bound_once_per_index_invocation(self) -> None:
        self.unit("src/shared.h", "#define SHARED_VALUE 3\n", "header")
        first = self.unit(
            "src/first.c",
            '#include "shared.h"\nint first(void) { return SHARED_VALUE; }\n',
            "first",
        )
        second = self.unit(
            "src/second.c",
            '#include "shared.h"\nint second(void) { return SHARED_VALUE; }\n',
            "second",
        )

        index = index_translation_units(self.root, [first, second])

        snapshot = index["parser"]["dependency_snapshot"]
        self.assertEqual(1, snapshot["unique_header_count"])
        self.assertEqual(1, snapshot["unique_header_fact_count"])
        self.assertEqual(1, len(index["header_facts"]))
        self.assertEqual(1, snapshot["header_misses"])
        self.assertEqual(1, snapshot["header_hits"])
        self.assertGreater(snapshot["path_resolution_hits"], 0)

    def test_large_function_span_sets_are_split_across_budgeted_facts(self) -> None:
        source = "".join(
            f"int function_{index}(void) {{ return {index}; }}\n"
            for index in range(160)
        )
        unit = self.unit("many.c", source, "many")

        index = index_translation_units(self.root, [unit])
        pages = build_context_pages(
            index, build_migration_graph(index),
            max_page_bytes=4_096, max_page_tokens=4_096,
        )

        span_facts = [
            fact for fact in pages["shared_facts"].values()
            if fact["kind"] == "translation_unit_function_spans"
        ]
        self.assertGreater(len(span_facts), 1)
        self.assertTrue(
            all(page["materialized_bytes"] <= 4_096 for page in pages["pages"])
        )

    def unit(self, relative: str, source: str, unit_id: str) -> dict:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = source.encode("utf-8")
        path.write_bytes(raw)
        return {
            "unit_id": unit_id,
            "source": {"path": relative, "sha256": hashlib.sha256(raw).hexdigest()},
        }


if __name__ == "__main__":
    unittest.main()
