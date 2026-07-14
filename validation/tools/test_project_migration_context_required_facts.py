from __future__ import annotations

import hashlib
import unittest

from validation.tools._project_migration_harness.context_contracts import canonical
from validation.tools._project_migration_harness.context_required_facts import (
    REQUIRED_FACT_QUERY_POLICY, build_required_fact_query,
    required_fact_resolution,
)
from validation.tools._project_migration_harness.context_retrieval import (
    partition_context_refs,
)
from validation.tools._project_migration_harness.context_selection import (
    select_deferred_context,
)


class ProjectMigrationRequiredFactTests(unittest.TestCase):
    def test_repo_header_declaration_closes_unresolved_call_query(self) -> None:
        facts, required, deferred = self.fixture(
            "int remote_step(int value);\n",
        )

        first = select_deferred_context(
            "group", required, deferred, facts, max_selected_bytes=8_192,
        )
        second = select_deferred_context(
            "group", list(reversed(required)), list(reversed(deferred)), facts,
            max_selected_bytes=8_192,
        )

        self.assertEqual(first, second)
        binding = first["binding"]
        self.assertEqual("ready", binding["selection_status"])
        self.assertEqual(REQUIRED_FACT_QUERY_POLICY,
                         binding["required_fact_query_policy"])
        self.assertEqual(1, binding["required_fact_query_count"])
        self.assertEqual(1, binding["required_fact_match_count"])
        self.assertEqual(0, binding["unresolved_required_fact_count"])
        self.assertTrue(first["selected_fact_refs"])

    def test_symbol_use_cannot_impersonate_a_declaration(self) -> None:
        facts, required, deferred = self.fixture(
            "int wrapper(int value) { return remote_step(value); }\n",
        )

        result = select_deferred_context(
            "group", required, deferred, facts, max_selected_bytes=8_192,
        )

        self.assertEqual("blocked", result["binding"]["selection_status"])
        self.assertEqual(
            ["required_fact_query_unresolved"],
            result["binding"]["selection_blockers"],
        )
        self.assertEqual(
            1, result["binding"]["unresolved_required_fact_count"],
        )

    def test_object_declaration_closes_unresolved_global_query(self) -> None:
        facts, required, deferred = self.fixture(
            "extern unsigned long remote_state;\n",
            fact_kind="global_reference",
        )

        result = select_deferred_context(
            "group", required, deferred, facts, max_selected_bytes=8_192,
        )

        self.assertEqual("ready", result["binding"]["selection_status"])
        self.assertEqual(1, result["binding"]["required_fact_match_count"])

    def test_object_use_in_initializer_cannot_close_global_query(self) -> None:
        facts, required, deferred = self.fixture(
            "static unsigned long local_state = remote_state;\n",
            fact_kind="global_reference",
        )

        result = select_deferred_context(
            "group", required, deferred, facts, max_selected_bytes=8_192,
        )

        self.assertEqual("blocked", result["binding"]["selection_status"])
        self.assertEqual(1, result["binding"]["unresolved_required_fact_count"])

    def test_required_match_omitted_by_budget_is_fail_closed(self) -> None:
        facts, required, deferred = self.fixture(
            "int remote_step(int value);\n",
        )

        result = select_deferred_context(
            "group", required, deferred, facts, max_selected_bytes=1,
        )

        self.assertEqual("blocked", result["binding"]["selection_status"])
        self.assertEqual([
            "exact_context_selection_budget_exceeded",
            "required_fact_query_unresolved",
        ], result["binding"]["selection_blockers"])
        self.assertEqual(0, result["binding"]["required_fact_match_count"])

    def test_required_query_sha_tamper_is_rejected(self) -> None:
        facts, required, deferred = self.fixture(
            "int remote_step(int value);\n",
        )
        query = build_required_fact_query("group", required, facts)
        query["sha256"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "SHA-256 drifted"):
            required_fact_resolution(query, [*required, *deferred], facts)

    def test_no_deferred_facts_cannot_bypass_required_query(self) -> None:
        facts, required, _deferred = self.fixture(None)

        visible, binding, retrieval_set, segments = partition_context_refs(
            "group", required, facts, self._adder(facts),
            max_selected_bytes=8_192,
            identifier_cache={},
            selection_index=self._selection_index(facts),
        )

        self.assertIsNotNone(binding)
        self.assertEqual("blocked", binding["selection_status"])
        self.assertEqual(1, binding["unresolved_required_fact_count"])
        self.assertEqual(0, retrieval_set["fact_count"])
        self.assertEqual({}, segments)
        self.assertGreater(len(visible), len(required))

    @staticmethod
    def fixture(
        header_content: str | None,
        *,
        fact_kind: str = "external_call",
    ) -> tuple[dict[str, dict], list[str], list[str]]:
        facts: dict[str, dict] = {}
        add = ProjectMigrationRequiredFactTests._adder(facts)
        symbol = "remote_state" if fact_kind == "global_reference" else "remote_step"
        required = [
            add("function", {
                "node_id": "node", "unit_id": "unit",
                "node_kind": "function", "symbol": "local_step",
                "linkage": "external",
            }),
            add("function_source", {
                "node_id": "node", "chunk_index": 0, "chunk_count": 1,
                "content": f"int local_step(void) {{ return {symbol}(1); }}",
            }),
        ]
        if fact_kind == "external_call":
            required.append(add("external_call", {
                "caller_node_id": "node", "symbol": symbol,
                "status": "unresolved_external", "candidate_node_ids": [],
            }))
        else:
            required.append(add("global_reference", {
                "node_id": "node", "symbol": symbol,
                "status": "unresolved_external", "global_ids": [],
            }))
        if header_content is None:
            return facts, required, []
        deferred = [
            add("include_binding", {
                "unit_id": "unit", "kind": "include", "body": '"api.h"',
                "sha256": "1" * 64, "byte_offset": 0,
                "from_path": "src/unit.c", "target": "api.h",
                "style": "quote", "status": "bound", "path": "include/api.h",
            }),
            add("header_source_binding", {
                "owner_id": "header-owner", "source": {
                    "path": "include/api.h", "sha256": "2" * 64,
                    "encoding": "utf-8", "span": {
                        "byte_start": 0, "byte_end": len(header_content),
                        "sha256": "3" * 64,
                    },
                },
            }),
            add("header_source", {
                "owner_id": "header-owner", "chunk_index": 0,
                "chunk_count": 1, "content": header_content,
            }),
        ]
        return facts, required, deferred

    @staticmethod
    def _adder(facts: dict[str, dict]):
        def add(kind: str, payload: dict) -> str:
            fact = {"kind": kind, "payload": payload}
            digest = hashlib.sha256(canonical(fact)).hexdigest()
            facts[digest] = fact
            return digest

        return add

    @staticmethod
    def _selection_index(facts: dict[str, dict]):
        from validation.tools._project_migration_harness.context_selection_index import (
            ContextSelectionIndex,
        )

        return ContextSelectionIndex(facts)


if __name__ == "__main__":
    unittest.main()
