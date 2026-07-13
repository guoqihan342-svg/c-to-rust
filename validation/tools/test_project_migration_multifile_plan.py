from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.orchestrator import plan_project


class ProjectMigrationMultifilePlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="project-multifile-plan-")
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.source = root / "unseen-source"
        self.harness = root / "harness"
        self.source.mkdir()
        self.harness.mkdir()

    def test_multifile_repository_builds_dependency_bound_worker_plan(self) -> None:
        self.write("include/public_api.h", "int helper(int value);\n")
        self.write(
            "src/helper.c",
            '#include "public_api.h"\nint helper(int value) { return value + 1; }\n',
        )
        self.write(
            "src/entry.c",
            '#include "public_api.h"\nint entry(int value) { return helper(value); }\n',
        )
        entries = [
            self.compile_entry("src/helper.c", "build/helper.o"),
            self.compile_entry("src/entry.c", "build/entry.o"),
        ]
        self.write("compile_commands.json", json.dumps(entries) + "\n")

        result = plan_project(
            self.source,
            harness_root=self.harness,
            out_root="target/unseen-run",
            run_id="unseen-multifile",
            source_commit="test-source-pin",
            max_units=8,
            max_concurrency=2,
            max_attempts=2,
        )

        self.assertEqual("planned", result["status"], result)
        output = self.harness / "target/unseen-run"
        discovery = self.read(output, "plan/discovery.json")
        self.assertEqual(2, len(discovery["translation_units"]))
        c_index = self.read(output, "plan/c-index.json")
        self.assertEqual(2, len(c_index["nodes"]))
        self.assertEqual(
            {"include/public_api.h"},
            {
                header["source"]["path"]
                for context in c_index["unit_contexts"]
                for header in context["headers"]
            },
        )
        graph = self.read(output, "plan/migration-graph.json")
        self.assertEqual(1, len(graph["resolved_call_edges"]))
        self.assertEqual(2, len(graph["sccs"]))
        self.assertTrue(any(item["dependency_scc_ids"] for item in graph["sccs"]))
        contexts = self.read(output, "plan/context-pages.json")
        self.assertIn(
            "header_source",
            {fact["kind"] for fact in contexts["shared_facts"].values()},
        )
        portfolio = self.read(output, "plan/portfolio.json")
        self.assertEqual(2, len(portfolio["ledger_units"]))
        self.assertEqual(
            {"translator", "reviewer", "repairer"},
            {item["role"] for item in portfolio["assignments"]},
        )
        self.assertTrue((output / "state/project-migration.sqlite3").is_file())
        self.assertFalse(result["claim_boundary"]["semantic_gate"])

    def compile_entry(self, source: str, output: str) -> dict[str, object]:
        return {
            "directory": ".",
            "file": source,
            "arguments": [
                "clang", "-Iinclude", "-c", source, "-o", output,
            ],
            "output": output,
        }

    def write(self, relative: str, content: str) -> Path:
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    @staticmethod
    def read(root: Path, relative: str) -> dict[str, object]:
        return json.loads((root / relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
