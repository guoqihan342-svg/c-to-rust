from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from validation.tools._project_migration_harness.c_index import index_translation_units
from validation.tools._project_migration_harness.context_pages import build_context_pages
from validation.tools._project_migration_harness.migration_graph import build_migration_graph


class ProjectMigrationGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="migration-graph-")
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_non_code_regions_cannot_spoof_symbols_or_calls(self) -> None:
        source = (
            "#define FORGED() \\\n"
            " int macro_shape(void) { return macro_call(); }\n"
            "/* int comment_shape(void) { return comment_call(); } */\n"
            "static int state = 3;\n"
            "static int inner(void) {\n"
            "  const char *text = \"int string_shape(void) { fake(); }\";\n"
            "  return state + (text[0] == '(');\n"
            "}\n"
            "int outer(void) { return inner(); }\n"
        )
        index = index_translation_units(self.root, [self._unit("src/one.c", source)])

        by_symbol = {item["symbol"]: item for item in index["nodes"]}
        self.assertEqual(set(by_symbol), {"inner", "outer"})
        self.assertEqual(by_symbol["inner"]["direct_calls"], [])
        self.assertEqual(by_symbol["inner"]["referenced_globals"], ["state"])
        self.assertEqual(by_symbol["outer"]["direct_calls"], ["inner"])
        structural = json.dumps(
            {"nodes": index["nodes"], "globals": index["globals"]},
            sort_keys=True,
        )
        self.assertNotIn("macro_shape", structural)
        self.assertNotIn("comment_shape", structural)

    def test_repository_and_hash_bindings_fail_closed(self) -> None:
        unit = self._unit("src/unit.c", "int unit(void) { return 0; }\n")
        wrong_hash = {**unit, "source": {**unit["source"], "sha256": "0" * 64}}
        with self.assertRaisesRegex(ValueError, "sha256 does not match"):
            index_translation_units(self.root, [wrong_hash])
        escaping = {"unit_id": "bounded-unit", "source": {
            "path": "../outside.c", "sha256": "0" * 64}}
        with self.assertRaisesRegex(ValueError, "repo-relative POSIX"):
            index_translation_units(self.root, [escaping])

    def test_static_resolution_and_ambiguous_externals_are_structural(self) -> None:
        first = self._unit("src/first.c", (
            "static int local_step(void) { return 1; }\n"
            "int combine(void) { return local_step() + shared_step(); }\n"
        ))
        second = self._unit("src/second.c", "int shared_step(void) { return 2; }\n")
        third = self._unit("src/third.c", "int shared_step(void) { return 3; }\n")
        index = index_translation_units(self.root, [first, second, third])
        graph = build_migration_graph(index)
        node_ids = {item["symbol"]: item["node_id"] for item in index["nodes"]
                     if item["symbol"] != "shared_step"}
        binding = next(item for item in graph["nodes"]
                       if item["node_id"] == node_ids["combine"])

        self.assertEqual(binding["resolved_calls"], [{
            "symbol": "local_step", "callee_node_id": node_ids["local_step"]}])
        self.assertEqual(binding["external_calls"][0]["status"], "ambiguous_external")
        self.assertEqual(len(binding["external_calls"][0]["candidate_node_ids"]), 2)
        scc = next(item for item in graph["sccs"]
                   if node_ids["combine"] in item["node_ids"])
        self.assertEqual(scc["classification"], "boundary_required")

    def test_scc_waves_and_classification_survive_complete_renaming(self) -> None:
        first = self._graph_shape("alpha", "src/alpha.c")
        second = self._graph_shape("renamed", "other/renamed.c")

        self.assertEqual(first, second)
        self.assertEqual(first["groups"], [
            {"classification": "context_group", "dependencies": 0, "members": 2},
            {"classification": "independent", "dependencies": 1, "members": 1},
        ])
        self.assertEqual(first["waves"], [1, 1])

    def test_parser_blockers_force_boundary_classification(self) -> None:
        unit = self._unit("src/incomplete.c", (
            "int visible(void) { return 1; }\n"
            "/* unterminated\n"
        ))
        index = index_translation_units(self.root, [unit])
        graph = build_migration_graph(index)

        self.assertEqual(index["status"], "ready_with_boundaries")
        self.assertEqual(index["parser"]["blockers"][0]["kind"], "unterminated_block_comment")
        self.assertEqual(graph["sccs"][0]["classification"], "boundary_required")
        self.assertIn("parser_blocker", graph["sccs"][0]["structural_reasons"])

    def test_context_pages_share_source_facts_and_enforce_both_budgets(self) -> None:
        operations = "".join("  total += value;\n" for _ in range(36))
        source = (
            "static int accumulate(int value) {\n"
            "  int total = value;\n" + operations +
            "  return total;\n}\n"
            "int project(int value) { return accumulate(value); }\n"
        )
        index = index_translation_units(self.root, [self._unit("src/paged.c", source)])
        graph = build_migration_graph(index)
        poisoned_graph = {**graph, "expected_actual": "must-not-leak"}
        with self.assertRaisesRegex(ValueError, "does not match"):
            build_context_pages(index, poisoned_graph, max_page_bytes=1800, max_page_tokens=700)
        pack = build_context_pages(
            {**index, "oracle_payload": "must-not-leak"},
            graph,
            max_page_bytes=1800,
            max_page_tokens=700,
        )

        self.assertNotIn("must-not-leak", json.dumps(pack, sort_keys=True))
        self.assertTrue(all(item["materialized_bytes"] <= 1800 for item in pack["pages"]))
        self.assertTrue(all(item["estimated_tokens"] <= 700 for item in pack["pages"]))
        all_refs = [ref for page in pack["pages"] for ref in page["fact_refs"]]
        self.assertGreater(len(all_refs), len(set(all_refs)))
        self.assertEqual(len(pack["shared_facts"]), len(set(pack["shared_facts"])))
        source_facts: dict[str, list[dict[str, Any]]] = {}
        for fact in pack["shared_facts"].values():
            if fact["kind"] == "function_source":
                payload = fact["payload"]
                source_facts.setdefault(payload["node_id"], []).append(payload)
        for node in index["nodes"]:
            chunks = sorted(source_facts[node["node_id"]], key=lambda item: item["chunk_index"])
            self.assertEqual("".join(item["content"] for item in chunks), node["source"]["content"])

    def _graph_shape(self, prefix: str, path: str) -> dict[str, Any]:
        first, second, third = (f"{prefix}_{suffix}" for suffix in ("one", "two", "three"))
        source = (
            f"static int {second}(int);\n"
            f"static int {first}(int n) {{ return n ? {second}(n - 1) : 0; }}\n"
            f"static int {second}(int n) {{ return n ? {first}(n - 1) : 0; }}\n"
            f"int {third}(int n) {{ return {first}(n); }}\n"
        )
        graph = build_migration_graph(index_translation_units(self.root, [self._unit(path, source)]))
        return {
            "groups": sorted(({
                "members": len(item["node_ids"]),
                "classification": item["classification"],
                "dependencies": len(item["dependency_scc_ids"]),
            } for item in graph["sccs"]), key=lambda item: item["members"], reverse=True),
            "waves": [len(item["scc_ids"]) for item in graph["waves"]],
        }

    def _unit(self, path: str, source: str) -> dict[str, Any]:
        target = self.root.joinpath(*path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = source.encode("utf-8")
        target.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        unit_id = hashlib.sha256(f"{path}:{digest}".encode("utf-8")).hexdigest()[:24]
        return {"unit_id": unit_id, "source": {"path": path, "sha256": digest}}


if __name__ == "__main__":
    unittest.main()
