from __future__ import annotations

from copy import deepcopy
import hashlib
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.context_frontier_state import (
    ContextFrontierProjection,
    FRONTIER_PENDING,
    FRONTIER_READY,
    build_initial_context_frontier,
    context_frontier_head_sha256,
    context_frontier_schedule_binding,
    validate_context_frontier_head,
    validate_context_frontier_schedule_binding,
)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def reference(label: str) -> dict[str, object]:
    return {
        "path": f"context/{label}.json",
        "sha256": digest(label),
        "size_bytes": len(label),
    }


def input_binding() -> dict[str, object]:
    return {
        "dag_sha256": digest("dag"),
        "group_sha256": digest("group"),
        "failure_fact_set_sha256": digest("failure-facts"),
        "selection_seed_sha256": digest("selection-seed"),
        "limits": {
            "context_byte_budget": 4096,
            "context_page_limit": 8,
            "context_token_budget": 2048,
        },
    }


def head(
    *, status: str = FRONTIER_READY, mode: str = "host_retrieval",
    overlay: object = None, schema_version: int = 2,
) -> dict[str, object]:
    binding = input_binding()
    pending = status == FRONTIER_PENDING
    static = mode == "static_context"
    value: dict[str, object] = {
        "schema_version": schema_version,
        "run_id": "frontier-v2-run",
        "unit_id": "unit-1",
        "status": status,
        "mode": mode,
        "query_epoch": 0,
        "input_binding": binding,
        "selection_input_sha256": content_sha256(binding),
        "catalog": reference("catalog"),
        "selection_receipt_sha256": (
            None if pending or static else digest("receipt")
        ),
        "materialized_page_set_sha256": (
            None if pending else digest("pages")
        ),
        "selection_materialization_sha256": (
            None if pending or static else digest("materialization")
        ),
    }
    if schema_version == 2:
        value["context_overlay"] = deepcopy(overlay)
    return value


def ready_retrieval() -> dict[str, object]:
    return {
        "selection_status": "ready",
        "selection_blockers": [],
        "selection_receipt_sha256": digest("initial-receipt"),
        "materialized_page_set_sha256": digest("initial-pages"),
        "selection_materialization_sha256": digest("initial-materialization"),
        "required_fact_query_policy": "host-required-symbol-facts-v1",
        "required_fact_query_sha256": digest("query"),
        "required_fact_query_count": 0,
        "required_fact_match_count": 0,
        "required_fact_match_set_sha256": digest("matches"),
        "unresolved_required_fact_count": 0,
        "unresolved_required_fact_set_sha256": digest("unresolved"),
    }


class ProjectMigrationContextFrontierStateV2Tests(unittest.TestCase):
    def test_initial_heads_are_v2_with_no_overlay(self) -> None:
        contexts = {
            "static": ({"catalog": reference("static"), "pages": []}, FRONTIER_READY),
            "pending": (
                {"catalog": reference("pending"), "retrieval": {}},
                FRONTIER_PENDING,
            ),
            "ready": (
                {"catalog": reference("ready"), "retrieval": ready_retrieval()},
                FRONTIER_READY,
            ),
        }
        limits = input_binding()["limits"]
        for label, (context, expected_status) in contexts.items():
            with self.subTest(label=label):
                frontier = build_initial_context_frontier(
                    run_id="initial-v2-run",
                    unit_id=f"unit-{label}",
                    dag_sha256=digest("initial-dag"),
                    group_sha256=digest(f"group-{label}"),
                    context=context,
                    limits=limits,
                )
                initial_head = frontier["initial_head"]
                self.assertEqual(2, initial_head["schema_version"])
                self.assertEqual(expected_status, initial_head["status"])
                self.assertIsNone(initial_head["context_overlay"])
                projection = ContextFrontierProjection(
                    expected_status,
                    0,
                    initial_head,
                    frontier["initial_head_sha256"],
                )
                schedule = context_frontier_schedule_binding(projection)
                self.assertIsNone(schedule["context_overlay"])
                self.assertEqual(
                    schedule, validate_context_frontier_schedule_binding(schedule),
                )

    def test_ready_host_head_and_schedule_carry_strict_overlay(self) -> None:
        overlay = reference("overlay")
        value = head(overlay=overlay)

        self.assertEqual(value, validate_context_frontier_head(value))
        projection = ContextFrontierProjection(
            FRONTIER_READY, 1, value, context_frontier_head_sha256(value),
        )
        schedule = context_frontier_schedule_binding(projection)
        self.assertEqual(overlay, schedule["context_overlay"])
        self.assertEqual(
            schedule, validate_context_frontier_schedule_binding(schedule),
        )

        invalid_references = {
            "non-string-path": {**overlay, "path": 7},
            "parent-path": {**overlay, "path": "../overlay.json"},
            "backslash-path": {**overlay, "path": "context\\overlay.json"},
            "uppercase-sha": {**overlay, "sha256": "A" * 64},
            "boolean-size": {**overlay, "size_bytes": True},
            "negative-size": {**overlay, "size_bytes": -1},
            "missing-size": {key: item for key, item in overlay.items()
                             if key != "size_bytes"},
            "extra-key": {**overlay, "status": "present"},
        }
        for label, invalid in invalid_references.items():
            with self.subTest(label=label):
                candidate = deepcopy(value)
                candidate["context_overlay"] = invalid
                with self.assertRaises(ValueError):
                    validate_context_frontier_head(candidate)

    def test_pending_and_static_frontiers_reject_overlay(self) -> None:
        overlay = reference("forbidden-overlay")
        cases = {
            "pending": head(status=FRONTIER_PENDING, overlay=overlay),
            "static": head(mode="static_context", overlay=overlay),
        }
        for label, invalid in cases.items():
            with self.subTest(label=label, surface="head"):
                with self.assertRaises(ValueError):
                    validate_context_frontier_head(invalid)

            valid = deepcopy(invalid)
            valid["context_overlay"] = None
            projection = ContextFrontierProjection(
                valid["status"], 0, valid, context_frontier_head_sha256(valid),
            )
            schedule = context_frontier_schedule_binding(projection)
            schedule["context_overlay"] = overlay
            with self.subTest(label=label, surface="schedule"):
                with self.assertRaises(ValueError):
                    validate_context_frontier_schedule_binding(schedule)

    def test_ready_host_version_zero_may_have_no_overlay(self) -> None:
        value = head()
        projection = ContextFrontierProjection(
            FRONTIER_READY, 0, value, context_frontier_head_sha256(value),
        )

        schedule = context_frontier_schedule_binding(projection)

        self.assertIsNone(schedule["context_overlay"])
        self.assertEqual(
            schedule, validate_context_frontier_schedule_binding(schedule),
        )

    def test_legacy_v1_head_and_schedule_remain_compatible(self) -> None:
        legacy_head = head(
            status=FRONTIER_PENDING, schema_version=1,
        )
        self.assertEqual(legacy_head, validate_context_frontier_head(legacy_head))
        self.assertEqual(
            content_sha256(legacy_head), context_frontier_head_sha256(legacy_head),
        )
        projection = ContextFrontierProjection(
            FRONTIER_PENDING,
            0,
            legacy_head,
            context_frontier_head_sha256(legacy_head),
        )
        current_schedule = context_frontier_schedule_binding(projection)
        legacy_schedule = deepcopy(current_schedule)
        legacy_schedule.pop("context_overlay")

        self.assertEqual(
            current_schedule,
            validate_context_frontier_schedule_binding(legacy_schedule),
        )

    def test_v2_head_requires_explicit_overlay_member(self) -> None:
        value = head()
        value.pop("context_overlay")

        with self.assertRaisesRegex(ValueError, "head shape"):
            validate_context_frontier_head(value)

        for invalid_version in (True, 2.0):
            with self.subTest(schema_version=invalid_version):
                invalid = head()
                invalid["schema_version"] = invalid_version
                with self.assertRaisesRegex(ValueError, "head header"):
                    validate_context_frontier_head(invalid)


if __name__ == "__main__":
    unittest.main()
