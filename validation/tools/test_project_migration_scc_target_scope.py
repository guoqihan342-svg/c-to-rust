from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.build_ir import (
    translation_units_for_index,
)
from validation.tools._project_migration_harness.c_index import (
    index_translation_units,
)
from validation.tools._project_migration_harness.migration_graph import (
    build_migration_graph,
)
from validation.tools._project_migration_harness.migration_target_scope import (
    derive_build_ir_target_scopes,
    derive_scc_target_scope,
    validate_scc_target_scope,
)
from validation.tools._project_migration_harness.migration_target_scope_reopen import (
    reopen_target_scope_bindings,
)
from validation.tools._project_migration_harness.orchestration_model import portfolio_dag
from validation.tools._project_migration_harness.orchestrator_finalize import (
    _integration_manifest,
)
from validation.tools._project_migration_harness.ledger_run_contract import _validated_target_scopes


class SccTargetScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="scc-target-scope-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        source = self.root / "src/unit.c"
        source.parent.mkdir(parents=True)
        source.write_text(
            "static int second(int value);\n"
            "static int first(int value) {\n"
            "  return value ? second(value - 1) : 0;\n"
            "}\n"
            "static int second(int value) {\n"
            "  return value ? first(value - 1) : 0;\n"
            "}\n"
            "int entry(int value) { return first(value); }\n",
            encoding="utf-8",
        )
        raw = source.read_bytes()
        self.build_ir = self._build_ir(hashlib.sha256(raw).hexdigest(), len(raw))
        self.c_index = index_translation_units(
            self.root, translation_units_for_index(self.build_ir),
        )

    def test_same_source_variants_keep_isolated_target_scopes(self) -> None:
        debug = derive_scc_target_scope(
            self.c_index, [self._node_id("variant-debug", "entry")],
        )
        release = derive_scc_target_scope(
            self.c_index, [self._node_id("variant-release", "entry")],
        )

        self.assertIsNotNone(debug)
        self.assertIsNotNone(release)
        assert debug is not None and release is not None
        self.assertEqual(["variant-debug"], debug["source_unit_ids"])
        self.assertEqual(["object-debug"], debug["object_target_ids"])
        self.assertEqual(
            ["archive-debug", "link-debug"], debug["reachable_target_ids"],
        )
        self.assertEqual(["link-debug"], debug["terminal_target_ids"])
        self.assertEqual("target-bound", debug["domain_status"])
        self.assertEqual(["variant-release"], release["source_unit_ids"])
        self.assertEqual(["object-release"], release["object_target_ids"])
        self.assertEqual(
            ["archive-release", "link-release"],
            release["reachable_target_ids"],
        )
        self.assertEqual(["link-release"], release["terminal_target_ids"])
        self.assertNotEqual(debug["scope_sha256"], release["scope_sha256"])

    def test_multiple_scc_nodes_from_one_unit_are_deduplicated(self) -> None:
        scope = derive_scc_target_scope(
            self.c_index,
            [
                self._node_id("variant-debug", "first"),
                self._node_id("variant-debug", "second"),
            ],
        )

        self.assertIsNotNone(scope)
        assert scope is not None
        self.assertEqual(["variant-debug"], scope["source_unit_ids"])
        self.assertEqual(["object-debug"], scope["object_target_ids"])
        self.assertEqual(1, len(scope["unit_scopes"]))
        self.assertEqual(scope, validate_scc_target_scope(scope))

    def test_scc_spanning_disjoint_target_domains_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "migration_target_scope_disjoint"):
            derive_scc_target_scope(
                self.c_index,
                [
                    self._node_id("variant-debug", "entry"),
                    self._node_id("variant-release", "entry"),
                ],
            )

    def test_scope_content_and_hash_tampering_are_rejected(self) -> None:
        scope = derive_scc_target_scope(
            self.c_index, [self._node_id("variant-debug", "entry")],
        )
        self.assertIsNotNone(scope)
        assert scope is not None

        content_tampered = copy.deepcopy(scope)
        content_tampered["terminal_target_ids"] = ["link-release"]
        with self.assertRaisesRegex(ValueError, "migration_target_scope_content_invalid"):
            validate_scc_target_scope(content_tampered)

        hash_tampered = copy.deepcopy(scope)
        hash_tampered["scope_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "migration_target_scope_content_invalid"):
            validate_scc_target_scope(hash_tampered)

    def test_build_ir_recomputation_matches_graph_scope(self) -> None:
        graph = build_migration_graph(self.c_index)
        node_id = self._node_id("variant-debug", "first")
        group = next(item for item in graph["sccs"] if node_id in item["node_ids"])

        rebuilt = derive_build_ir_target_scopes(
            [self.build_ir],
            {group["scc_id"]: group["source_unit_ids"]},
        )

        self.assertEqual(group["target_scope"], rebuilt[group["scc_id"]])
        self.assertEqual(
            group["target_scope"],
            validate_scc_target_scope(rebuilt[group["scc_id"]]),
        )

    def test_scope_survives_graph_portfolio_and_manifest_round_trip(self) -> None:
        graph = build_migration_graph(self.c_index)
        dag = portfolio_dag(graph, {}, run_id="run", project_key="project")
        reference = {"path": "plan/artifact.json", "sha256": "a" * 64,
                     "size_bytes": 1}
        artifacts = {
            key: reference for key in (
                "generated_build_closure", "generated_build_closure_verification",
                "build_ir", "build_ir_verification", "build_ir_worker_admission",
                "c_compilation_facts", "migration_graph", "project_test_inventory",
            )
        }

        manifest = _integration_manifest(
            "competition", dag, artifacts, True, True,
            {"ledger_units": [
                {"unit_id": item["group_id"],
                 "content_sha256": item["content_sha256"]}
                for item in dag["groups"]
            ]},
        )
        reopened = reopen_target_scope_bindings(manifest, [self.build_ir], graph)

        self.assertIsNotNone(reopened)
        assert reopened is not None
        self.assertEqual(len(graph["sccs"]), reopened["group_count"])
        self.assertEqual(set(manifest["dag"]), set(manifest["target_scopes"]))
        by_group = {item["group_id"]: item for item in dag["groups"]}
        self.assertTrue(all(
            binding["group_content_sha256"] == by_group[group_id]["content_sha256"]
            for group_id, binding in manifest["target_scopes"].items()
        ))
        self.assertTrue(all(
            binding["scope_sha256"] == by_group[group_id]["target_scope"]["scope_sha256"]
            for group_id, binding in manifest["target_scopes"].items()
        ))
        wave_by_group = {
            group_id: wave["wave_index"] for wave in dag["waves"]
            for group_id in wave["group_ids"]
        }
        units = [{"unit_id": item["group_id"], "group_id": item["group_id"],
                  "wave_index": wave_by_group[item["group_id"]],
                  "content_sha256": item["content_sha256"]}
                 for item in dag["groups"]]
        _validated_target_scopes(manifest, units)
        tampered = copy.deepcopy(manifest)
        first = sorted(tampered["target_scopes"])[0]
        tampered["target_scopes"][first]["group_content_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "group binding drifted"):
            _validated_target_scopes(tampered, units)

    def _node_id(self, unit_id: str, symbol: str) -> str:
        return next(
            item["node_id"] for item in self.c_index["nodes"]
            if item["unit_id"] == unit_id and item["symbol"] == symbol
        )

    @staticmethod
    def _build_ir(source_sha: str, source_size: int) -> dict:
        units = []
        targets = []
        for index, label in enumerate(("debug", "release")):
            unit_id = f"variant-{label}"
            object_id = f"object-{label}"
            archive_id = f"archive-{label}"
            link_id = f"link-{label}"
            output = f"build/{label}/unit.o"
            units.append({
                "unit_id": unit_id,
                "variant_index": index,
                "variant_count": 2,
                "source": {
                    "path": "src/unit.c",
                    "kind": "file",
                    "materialized": True,
                    "sha256": source_sha,
                    "size_bytes": source_size,
                },
                "working_directory": ".",
                "compiler": "clang",
                "compiler_wrappers": [],
                "toolchain_id": "toolchain",
                "language": "c",
                "includes": [],
                "defines": [{"name": "MODE", "value": str(index)}],
                "redacted_define_count": 0,
                "compile_arguments": {
                    "semantic_flags": [f"-O{index}"],
                    "expanded_argv_sha256": "a" * 64,
                    "response_files": [],
                },
                "output": {
                    "path": output,
                    "kind": "file",
                    "materialized": False,
                },
                "provenance": {
                    "entry_index": index,
                    "entry_sha256": "b" * 64,
                },
            })
            targets.extend([
                SccTargetScopeTests._target(
                    object_id, "object", output, [], [None], [], unit_id,
                ),
                SccTargetScopeTests._target(
                    archive_id,
                    "archive",
                    f"build/{label}/libunit.a",
                    [object_id],
                    [object_id],
                    [],
                    None,
                ),
                SccTargetScopeTests._target(
                    link_id,
                    "link",
                    f"build/{label}/app",
                    [archive_id],
                    [archive_id],
                    [f"-Wl,--build-id={label}"],
                    None,
                ),
            ])
        return {"translation_units": units, "targets": targets}

    @staticmethod
    def _target(
        identifier: str,
        kind: str,
        output: str,
        dependencies: list[str],
        ordered_inputs: list[str | None],
        link_arguments: list[str],
        unit_id: str | None,
    ) -> dict:
        provenance = {} if unit_id is None else {"unit_id": unit_id}
        return {
            "target_id": identifier,
            "name": output,
            "kind": kind,
            "outputs": [{"path": output}],
            "ordered_inputs": [
                {"dependency_target_id": value} for value in ordered_inputs
            ],
            "dependency_target_ids": dependencies,
            "compile_argument_sets": [],
            "ordered_link_arguments": link_arguments,
            "provenance": provenance,
        }


if __name__ == "__main__":
    unittest.main()
