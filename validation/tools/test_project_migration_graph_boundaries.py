from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.c_index import index_translation_units
from validation.tools._project_migration_harness.context_pages import build_context_pages
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
        self.assertEqual("translation_unit_boundary", index["nodes"][0]["node_kind"])
        self.assertEqual(
            (self.root / "conditional.c").read_text(encoding="utf-8"),
            index["nodes"][0]["source"]["content"],
        )
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
        self.assertEqual("src/config.h", context["headers"][0]["source"]["path"])
        self.assertEqual("complete", context["top_level"]["coverage"]["status"])
        state = next(item for item in index["globals"] if item["symbol"] == "state")
        self.assertEqual("static int state = INITIAL_VALUE;", state["source"]["content"])
        graph = build_migration_graph(index)
        pages = build_context_pages(index, graph)
        kinds = {fact["kind"] for fact in pages["shared_facts"].values()}
        self.assertTrue({"header_source", "global_source", "translation_unit_coverage"} <= kinds)

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
        self.assertEqual("translation_unit_boundary", index["nodes"][0]["node_kind"])
        graph = build_migration_graph(index)
        self.assertEqual("boundary_required", graph["sccs"][0]["classification"])

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
