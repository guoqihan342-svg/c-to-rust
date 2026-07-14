from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path, PurePosixPath
import tempfile
import unittest

from validation.tools._project_migration_harness.context_frontier import (
    materialize_scheduled_contexts,
)
from validation.tools._project_migration_harness.context_frontier_state import (
    ContextFrontierProjection, build_initial_context_frontier,
    context_frontier_schedule_binding,
)
from validation.tools._project_migration_harness.context_frontier_runtime import (
    validate_request_context_materialization,
)
from validation.tools._project_migration_harness.artifacts import (
    canonical_json_bytes, content_sha256,
)
from validation.tools._project_migration_harness.orchestrator import plan_project


class ProjectMigrationContextFrontierTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="context-frontier-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.source = root / "source"
        self.harness = root / "harness"
        self.output = self.harness / "target/frontier"
        self.source.mkdir()
        self.harness.mkdir()

    def test_plan_materializes_only_initial_frontier_then_dispatch_adds_group(self) -> None:
        plan = self.plan()
        report = self.read_local(plan["artifacts"]["context_materialization"])
        self.assertEqual(2, report["logical_group_count"])
        self.assertEqual(0, report["selected_group_count"])
        self.assertEqual(0, report["materialized_page_count"])
        self.assertLess(
            report["materialized_page_count"], report["logical_page_count"],
        )
        self.assertEqual(
            2,
            len(list((self.output / "context/catalog/groups").glob("*.json"))),
        )

        assignment = plan["portfolio"]["assignments"][0]
        page_paths = [
            self.harness.joinpath(*PurePosixPath(page["path"]).parts)
            for page in assignment["context"]["pages"]
        ]
        self.assertTrue(page_paths)
        self.assertTrue(all(not path.exists() for path in page_paths))

        refs, materialization = materialize_scheduled_contexts(
            {"ready": [self.ready(plan, assignment)]},
            harness_root=self.harness,
            out_root=self.output,
            out_root_rel="target/frontier",
        )

        self.assertEqual(len(page_paths), len(refs))
        self.assertTrue(all(path.is_file() for path in page_paths))
        receipt = self.read_local(materialization)
        self.assertEqual([assignment["group_id"]], receipt["selected_group_ids"])
        self.assertEqual(
            "content-addressed-write-once-idempotent",
            receipt["write_policy"],
        )
        repeated_refs, repeated = materialize_scheduled_contexts(
            {"ready": [self.ready(plan, assignment)]},
            harness_root=self.harness,
            out_root=self.output,
            out_root_rel="target/frontier",
        )
        self.assertEqual(refs, repeated_refs)
        self.assertEqual(materialization, repeated)

        first_bytes = {path: path.read_bytes() for path in page_paths}
        second = next(
            item for item in plan["portfolio"]["assignments"]
            if item["group_id"] != assignment["group_id"]
        )
        second_paths = [
            self.harness.joinpath(*PurePosixPath(page["path"]).parts)
            for page in second["context"]["pages"]
        ]
        materialize_scheduled_contexts(
            {"ready": [self.ready(plan, second)]},
            harness_root=self.harness,
            out_root=self.output,
            out_root_rel="target/frontier",
        )
        self.assertTrue(all(path.is_file() for path in second_paths))
        self.assertEqual(first_bytes, {
            path: path.read_bytes() for path in page_paths
        })

    def test_catalog_tamper_is_rejected_before_page_materialization(self) -> None:
        plan = self.plan()
        assignment = plan["portfolio"]["assignments"][0]
        catalog = self.harness.joinpath(
            *PurePosixPath(assignment["context"]["catalog"]["path"]).parts
        )
        catalog.write_text("{}\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "SHA-256 drifted"):
            materialize_scheduled_contexts(
                {"ready": [self.ready(plan, assignment)]},
                harness_root=self.harness,
                out_root=self.output,
                out_root_rel="target/frontier",
            )
        self.assertTrue(all(
            not self.harness.joinpath(*PurePosixPath(page["path"]).parts).exists()
            for page in assignment["context"]["pages"]
        ))

    def test_static_context_page_set_stays_bound_through_runtime(self) -> None:
        plan = self.plan()
        assignment = deepcopy(plan["portfolio"]["assignments"][0])
        context = assignment["context"]
        context.pop("retrieval", None)
        catalog_path = self.harness.joinpath(
            *PurePosixPath(context["catalog"]["path"]).parts
        )
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        catalog["retrieval"] = None
        catalog_bytes = canonical_json_bytes(catalog)
        catalog_path.write_bytes(catalog_bytes)
        context["catalog"] = {
            **context["catalog"],
            "sha256": content_sha256(catalog),
            "size_bytes": len(catalog_bytes),
        }
        frontier = build_initial_context_frontier(
            run_id=plan["run_id"], unit_id=assignment["unit_id"],
            dag_sha256=plan["portfolio"]["dag_sha256"],
            group_sha256=assignment["group_sha256"], context=context,
            limits=plan["portfolio"]["limits"],
        )
        projection = ContextFrontierProjection(
            frontier["initial_status"], 0, frontier["initial_head"],
            frontier["initial_head_sha256"],
        )
        binding = context_frontier_schedule_binding(projection)
        _refs, materialization = materialize_scheduled_contexts(
            {"ready": [{"assignment": assignment, "context_frontier": binding}]},
            harness_root=self.harness, out_root=self.output,
            out_root_rel="target/frontier",
        )
        report = self.read_local(materialization)
        self.assertEqual(
            binding["materialized_page_set_sha256"],
            report["groups"][0]["materialized_page_set_sha256"],
        )
        request = {
            "worker_id": assignment["worker_id"],
            "role": assignment["role"],
            "group_id": assignment["group_id"],
            "context": context,
            "context_frontier": binding,
            "assignment_binding": {
                "assignment_sha256": content_sha256(assignment),
            },
            "context_materialization": {
                **materialization,
                "path": f"target/frontier/{materialization['path']}",
            },
        }
        validate_request_context_materialization(
            request, harness_root=self.harness,
        )

    def test_partial_previous_materialization_fails_closed(self) -> None:
        plan = self.plan()
        assignment = plan["portfolio"]["assignments"][0]
        catalog_path = self.harness.joinpath(*PurePosixPath(
            assignment["context"]["catalog"]["path"]
        ).parts)
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        page = catalog["pages"][0]
        target = self.output.joinpath(*PurePosixPath(
            page["reference"]["path"]
        ).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                page["payload"], ensure_ascii=True, sort_keys=True,
                separators=(",", ":"),
            ) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "materialization is incomplete"):
            materialize_scheduled_contexts(
                {"ready": [self.ready(plan, assignment)]},
                harness_root=self.harness,
                out_root=self.output,
                out_root_rel="target/frontier",
            )

    def test_existing_page_drift_is_not_silently_repaired(self) -> None:
        plan = self.plan()
        assignment = plan["portfolio"]["assignments"][0]
        schedule = {"ready": [self.ready(plan, assignment)]}
        materialize_scheduled_contexts(
            schedule,
            harness_root=self.harness,
            out_root=self.output,
            out_root_rel="target/frontier",
        )
        page = self.harness.joinpath(*PurePosixPath(
            assignment["context"]["pages"][0]["path"]
        ).parts)
        page.write_text("{}\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "materialized page drifted"):
            materialize_scheduled_contexts(
                schedule,
                harness_root=self.harness,
                out_root=self.output,
                out_root_rel="target/frontier",
            )

    def test_existing_group_index_drift_is_not_silently_accepted(self) -> None:
        plan = self.plan()
        assignment = plan["portfolio"]["assignments"][0]
        schedule = {"ready": [self.ready(plan, assignment)]}
        materialize_scheduled_contexts(
            schedule,
            harness_root=self.harness,
            out_root=self.output,
            out_root_rel="target/frontier",
        )
        group = self.output / f"context/groups/{assignment['group_id']}.json"
        payload = json.loads(group.read_text(encoding="utf-8"))
        payload["model_input_policy"] = {"tampered": True}
        group.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "group index drifted"):
            materialize_scheduled_contexts(
                schedule,
                harness_root=self.harness,
                out_root=self.output,
                out_root_rel="target/frontier",
            )

    def plan(self) -> dict:
        (self.source / "unit.c").write_text(
            "int alpha(int value) { return value + 1; }\n"
            "int beta(int value) { return value * 2; }\n",
            encoding="utf-8",
        )
        database = self.source / "compile_commands.json"
        database.write_text(json.dumps([{
            "directory": ".",
            "file": "unit.c",
            "arguments": ["clang", "-c", "unit.c", "-o", "unit.o"],
            "output": "unit.o",
        }]), encoding="utf-8")
        return plan_project(
            self.source,
            harness_root=self.harness,
            out_root="target/frontier",
            compile_database=database,
            run_id="frontier-run",
            max_concurrency=1,
        )

    def read_local(self, reference: dict) -> dict:
        return json.loads(
            (self.output / Path(*PurePosixPath(reference["path"]).parts))
            .read_text(encoding="utf-8")
        )

    @staticmethod
    def ready(plan: dict, assignment: dict) -> dict:
        frontier = next(
            item for item in plan["portfolio"]["context_frontiers"]
            if item["unit_id"] == assignment["unit_id"]
        )
        projection = ContextFrontierProjection(
            frontier["initial_status"], 0, frontier["initial_head"],
            frontier["initial_head_sha256"],
        )
        return {
            "assignment": assignment,
            "context_frontier": context_frontier_schedule_binding(projection),
        }


if __name__ == "__main__":
    unittest.main()
