from __future__ import annotations

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
from validation.tools._project_migration_harness.context_pages import (
    build_context_pages,
)
from validation.tools._project_migration_harness.c_index_build_targets import (
    normalized_build_target_context,
)
from validation.tools._project_migration_harness.migration_graph import (
    build_migration_graph,
)


class VariantTargetContextTests(unittest.TestCase):
    def test_variants_keep_distinct_target_membership_in_context_pack(self) -> None:
        with tempfile.TemporaryDirectory(prefix="variant-target-context-") as temporary:
            root = Path(temporary)
            source = root / "src/unit.c"
            source.parent.mkdir()
            source.write_text("int unit(void) { return 1; }\n", encoding="utf-8")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            build_ir = self._build_ir(digest, source.stat().st_size)

            projected = translation_units_for_index(build_ir)
            contexts = {
                item["unit_id"]: item["build_target_context"]
                for item in projected
            }
            self.assertEqual({0, 1}, {
                item["variant"]["index"] for item in contexts.values()
            })
            self.assertEqual({2}, {
                item["variant"]["count"] for item in contexts.values()
            })
            self.assertEqual(
                {"link-debug", "link-release"},
                {
                    item["consumer_targets"][1]["target_id"]
                    for item in contexts.values()
                },
            )
            self.assertEqual(
                {"archive-debug", "archive-release"},
                {
                    item["consumer_targets"][0]["target_id"]
                    for item in contexts.values()
                },
            )

            index = index_translation_units(root, projected)
            graph = build_migration_graph(index)
            self.assertEqual([], graph["external_calls"])
            self.assertTrue(all(
                "ambiguous_external_definition" not in item["structural_reasons"]
                for item in graph["sccs"]
            ))
            pages = build_context_pages(index, graph)
            facts = list(pages["shared_facts"].values())
            membership = [
                item["payload"] for item in facts
                if item["kind"] == "build_target_membership"
            ]
            targets = [
                item["payload"] for item in facts
                if item["kind"] == "build_target"
            ]
            self.assertEqual(2, len(membership))
            self.assertEqual(6, len(targets))
            self.assertEqual(
                {"object-debug", "object-release"},
                {item["object_target_id"] for item in membership},
            )
            self.assertEqual(
                {
                    ("archive-debug", "link-debug"),
                    ("archive-release", "link-release"),
                },
                {tuple(item["consumer_target_ids"]) for item in membership},
            )

    def test_variant_cardinality_mismatch_fails_closed(self) -> None:
        build_ir = self._build_ir("a" * 64, 1)
        build_ir["translation_units"][1]["variant_count"] = 3

        with self.assertRaisesRegex(ValueError, "build_ir_index_variant_invalid"):
            translation_units_for_index(build_ir)

    def test_orphan_object_target_fails_closed(self) -> None:
        build_ir = self._build_ir("a" * 64, 1)
        build_ir["targets"][0]["outputs"][0]["path"] = "build/debug/orphan.o"

        with self.assertRaisesRegex(ValueError, "object_target_orphan"):
            translation_units_for_index(build_ir)

    def test_reachable_target_cycle_fails_closed(self) -> None:
        build_ir = self._build_ir("a" * 64, 1)
        build_ir["targets"][1]["dependency_target_ids"].append("link-debug")

        with self.assertRaisesRegex(ValueError, "build_ir_index_target_cycle"):
            translation_units_for_index(build_ir)

    def test_reopener_rejects_unreachable_consumer(self) -> None:
        context = translation_units_for_index(
            self._build_ir("a" * 64, 1)
        )[0]["build_target_context"]
        context["consumer_targets"][1]["dependency_target_ids"] = ["unrelated"]
        context["consumer_targets"][1]["ordered_input_target_ids"] = ["unrelated"]

        with self.assertRaisesRegex(ValueError, "consumer target binding"):
            normalized_build_target_context(context, unit_id="variant-debug")

    def test_overlapping_target_domain_keeps_duplicate_definition_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory(prefix="variant-target-overlap-") as temporary:
            root = Path(temporary)
            source = root / "src/unit.c"
            source.parent.mkdir()
            source.write_text("int unit(void) { return 1; }\n", encoding="utf-8")
            build_ir = self._build_ir(
                hashlib.sha256(source.read_bytes()).hexdigest(), source.stat().st_size,
            )
            release_link = build_ir["targets"][5]
            release_link["dependency_target_ids"].append("archive-debug")
            release_link["ordered_inputs"].append({
                "dependency_target_id": "archive-debug",
            })

            graph = build_migration_graph(index_translation_units(
                root, translation_units_for_index(build_ir),
            ))

            self.assertEqual(2, sum(
                "ambiguous_external_definition" in item["structural_reasons"]
                for item in graph["sccs"]
            ))

    def test_partially_bound_target_domains_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="variant-target-partial-") as temporary:
            root = Path(temporary)
            source = root / "src/unit.c"
            source.parent.mkdir()
            source.write_text("int unit(void) { return 1; }\n", encoding="utf-8")
            projected = translation_units_for_index(self._build_ir(
                hashlib.sha256(source.read_bytes()).hexdigest(), source.stat().st_size,
            ))
            projected[1].pop("build_target_context")
            index = index_translation_units(root, projected)

            with self.assertRaisesRegex(ValueError, "target_domains_incomplete"):
                build_migration_graph(index)

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
            source = {
                "path": "src/unit.c", "kind": "file", "materialized": True,
                "sha256": source_sha, "size_bytes": source_size,
            }
            units.append({
                "unit_id": unit_id, "variant_index": index, "variant_count": 2,
                "source": source, "working_directory": ".", "compiler": "clang",
                "compiler_wrappers": [], "toolchain_id": "toolchain",
                "language": "c", "includes": [],
                "defines": [{"name": "MODE", "value": str(index)}],
                "redacted_define_count": 0,
                "compile_arguments": {
                    "semantic_flags": [f"-O{index}"],
                    "expanded_argv_sha256": "a" * 64, "response_files": [],
                },
                "output": {"path": output, "kind": "file", "materialized": False},
                "provenance": {"entry_index": index, "entry_sha256": "b" * 64},
            })
            targets.extend([
                VariantTargetContextTests._target(
                    object_id, "object", output, [], [None], [], unit_id,
                ),
                VariantTargetContextTests._target(
                    archive_id, "archive", f"build/{label}/libunit.a", [object_id],
                    [object_id], [], None,
                ),
                VariantTargetContextTests._target(
                    link_id, "link", f"build/{label}/app", [archive_id],
                    [archive_id], [f"-Wl,--build-id={label}"], None,
                ),
            ])
        return {"translation_units": units, "targets": targets}

    @staticmethod
    def _target(
        identifier: str, kind: str, output: str, dependencies: list[str],
        ordered_inputs: list[str | None], link_arguments: list[str],
        unit_id: str | None,
    ) -> dict:
        provenance = {} if unit_id is None else {"unit_id": unit_id}
        return {
            "target_id": identifier, "name": output, "kind": kind,
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
