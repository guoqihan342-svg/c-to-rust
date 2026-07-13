from __future__ import annotations

import hashlib
import unittest

from validation.tools._project_migration_harness.context_contracts import canonical
from validation.tools._project_migration_harness.context_selection import (
    select_deferred_context,
)


class ProjectMigrationContextSelectionTests(unittest.TestCase):
    def test_exact_direct_header_symbol_is_selected_deterministically(self) -> None:
        facts, required, deferred = self.fixture()

        first = select_deferred_context(
            "group", required, deferred, facts, max_selected_bytes=8_192
        )
        second = select_deferred_context(
            "group", list(reversed(required)), list(reversed(deferred)), facts,
            max_selected_bytes=8_192,
        )

        self.assertEqual(first, second)
        self.assertEqual("ready", first["binding"]["selection_status"])
        self.assertEqual(set(deferred), set(first["selected_fact_refs"]))
        self.assertEqual([], first["omitted_fact_refs"])

    def test_exact_match_that_cannot_fit_blocks_selection(self) -> None:
        facts, required, deferred = self.fixture()

        result = select_deferred_context(
            "group", required, deferred, facts, max_selected_bytes=1
        )

        self.assertEqual("blocked", result["binding"]["selection_status"])
        self.assertEqual(
            ["exact_context_selection_budget_exceeded"],
            result["binding"]["selection_blockers"],
        )
        self.assertEqual(set(deferred), set(result["omitted_fact_refs"]))

    @staticmethod
    def fixture() -> tuple[dict[str, dict], list[str], list[str]]:
        facts: dict[str, dict] = {}

        def add(kind: str, payload: dict) -> str:
            fact = {"kind": kind, "payload": payload}
            digest = hashlib.sha256(canonical(fact)).hexdigest()
            facts[digest] = fact
            return digest

        required = [
            add("function", {
                "node_id": "node", "unit_id": "unit", "node_kind": "function",
                "symbol": "read_api", "linkage": "external",
            }),
            add("source_binding", {
                "node_id": "node", "source": {
                    "path": "src/main.c", "sha256": "1" * 64,
                    "encoding": "utf-8", "span": {
                        "byte_start": 0, "byte_end": 1, "sha256": "2" * 64,
                    },
                },
            }),
            add("function_source", {
                "node_id": "node", "chunk_index": 0, "chunk_count": 1,
                "content": "int read_api(void) { return API_VALUE; }",
            }),
        ]
        deferred = [
            add("include_binding", {
                "unit_id": "unit", "kind": "include", "body": '"api.h"',
                "sha256": "3" * 64, "byte_offset": 0,
                "from_path": "src/main.c", "target": "api.h",
                "style": "quote", "status": "bound", "path": "src/api.h",
            }),
            add("header_source_binding", {
                "owner_id": "header-owner", "source": {
                    "path": "src/api.h", "sha256": "4" * 64,
                    "encoding": "utf-8", "span": {
                        "byte_start": 0, "byte_end": 20, "sha256": "4" * 64,
                    },
                },
            }),
            add("header_source", {
                "owner_id": "header-owner", "chunk_index": 0, "chunk_count": 1,
                "content": "#define API_VALUE 9\n",
            }),
        ]
        return facts, required, deferred


if __name__ == "__main__":
    unittest.main()
