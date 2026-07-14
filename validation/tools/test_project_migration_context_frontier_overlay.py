from __future__ import annotations

from copy import deepcopy
import unittest

from validation.tools._project_migration_harness.artifacts import (
    canonical_json_bytes, content_sha256,
)
from validation.tools._project_migration_harness.context_frontier_overlay import (
    build_context_frontier_overlay, resolve_effective_context,
    validate_context_frontier_overlay,
)


def _sha(label: str) -> str:
    return content_sha256({"label": label})


def _reference(path: str, label: str) -> dict:
    return {"path": path, "sha256": _sha(label), "size_bytes": len(label)}


class ProjectMigrationContextFrontierOverlayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_catalog = _reference(
            "target/context/catalog/unit-a.json", "base-catalog",
        )
        self.catalog = _reference(
            "target/context/frontier-cas/catalogs/unit-a.json", "refreshed-catalog",
        )
        self.outputs = {
            "selection_receipt_sha256": _sha("receipt"),
            "materialized_page_set_sha256": _sha("pages"),
            "selection_materialization_sha256": _sha("materialization"),
        }
        self.context = {
            "catalog": deepcopy(self.catalog),
            "retrieval": {"selection_status": "ready", **self.outputs},
            "pages": [{"page_id": "page-a", "sha256": _sha("page-a")}],
        }
        self.base_frontier = {
            "status": "pending_retrieval",
            "state_version": 7,
            "head_sha256": _sha("pending-head"),
            "query_epoch": 3,
            "catalog": deepcopy(self.base_catalog),
        }
        self.assignments = [
            self.assignment(role) for role in (
                "translator", "repairer", "planner", "reviewer",
            )
        ]
        self.overlay = build_context_frontier_overlay(
            self.assignments,
            self.base_frontier,
            plan_sha256=_sha("plan"),
            refresh_bundle=_reference(
                "target/context/refresh/unit-a-3.json", "refresh",
            ),
            effective_context=self.context,
        )

    @staticmethod
    def assignment(role: str, *, unit_id: str = "unit-a") -> dict:
        return {
            "run_id": "run-a",
            "unit_id": unit_id,
            "group_id": unit_id,
            "role": role,
            "worker_id": f"worker-{unit_id}-{role}",
            "immutable_input": {"role": role, "unit_id": unit_id},
        }

    def frontier(self, overlay: dict | None = None) -> dict:
        value = self.overlay if overlay is None else overlay
        return {
            "status": "ready",
            "query_epoch": value["query_epoch"],
            "catalog": deepcopy(value["effective_context"]["catalog"]),
            **{field: value[field] for field in self.outputs},
            "context_overlay": {
                "path": "target/context/overlays/unit-a-3.json",
                "sha256": content_sha256(value),
                "size_bytes": len(canonical_json_bytes(value)),
            },
        }

    def test_unit_overlay_binds_sorted_assignment_set_and_resolves_each_role(self) -> None:
        records = self.overlay["assignment_digests"]
        self.assertEqual(
            sorted((item["role"], item["worker_id"]) for item in records),
            [(item["role"], item["worker_id"]) for item in records],
        )
        self.assertEqual(
            content_sha256(records), self.overlay["assignment_set_sha256"],
        )
        self.assertEqual({"unit-a"}, {item["unit_id"] for item in records})
        self.assertEqual(self.context, self.overlay["effective_context"])
        self.assertNotEqual(
            self.overlay["base_frontier"]["catalog"],
            self.overlay["effective_context"]["catalog"],
        )
        self.assertEqual(
            content_sha256(self.context), self.overlay["context_sha256"],
        )
        self.assertEqual(
            {"semantic_gate": False, "translation_coverage_numerator": 0},
            self.overlay["claim_boundary"],
        )
        self.assertEqual(self.overlay, validate_context_frontier_overlay(self.overlay))

        frontier = self.frontier()
        for assignment in self.assignments:
            with self.subTest(role=assignment["role"]):
                self.assertEqual(
                    self.context,
                    resolve_effective_context(assignment, frontier, self.overlay),
                )

    def test_builder_rejects_assignments_from_more_than_one_unit(self) -> None:
        assignments = [*self.assignments, self.assignment("reviewer", unit_id="unit-b")]
        with self.assertRaisesRegex(ValueError, "span units"):
            build_context_frontier_overlay(
                assignments,
                self.base_frontier,
                plan_sha256=_sha("plan"),
                refresh_bundle=_reference("target/refresh.json", "refresh"),
                effective_context=self.context,
            )

    def test_builder_rejects_query_epoch_and_invalid_effective_catalog(self) -> None:
        with self.assertRaisesRegex(ValueError, "query epoch drifted"):
            build_context_frontier_overlay(
                self.assignments,
                self.base_frontier,
                plan_sha256=_sha("plan"),
                refresh_bundle=_reference("target/refresh.json", "refresh"),
                effective_context=self.context,
                query_epoch=4,
            )
        context = deepcopy(self.context)
        context["catalog"]["path"] = "../other-catalog.json"
        with self.assertRaisesRegex(ValueError, "stay relative"):
            build_context_frontier_overlay(
                self.assignments,
                self.base_frontier,
                plan_sha256=_sha("plan"),
                refresh_bundle=_reference("target/refresh.json", "refresh"),
                effective_context=context,
            )

    def test_validator_enforces_strict_field_sets(self) -> None:
        cases = []
        extra = deepcopy(self.overlay)
        extra["unexpected"] = None
        cases.append(extra)
        nested = deepcopy(self.overlay)
        nested["refresh_bundle"]["status"] = "present"
        cases.append(nested)
        record = deepcopy(self.overlay)
        record["assignment_digests"][0]["unexpected"] = None
        cases.append(record)
        base = deepcopy(self.overlay)
        base["base_frontier"]["status"] = "pending_retrieval"
        cases.append(base)
        boundary = deepcopy(self.overlay)
        boundary["claim_boundary"]["translation_coverage_numerator"] = False
        cases.append(boundary)
        for value in cases:
            with self.subTest(keys=sorted(value)):
                with self.assertRaises(ValueError):
                    validate_context_frontier_overlay(value)

        wrong_unit = deepcopy(self.overlay)
        wrong_unit["assignment_digests"][0]["unit_id"] = "unit-b"
        wrong_unit["assignment_set_sha256"] = content_sha256(
            wrong_unit["assignment_digests"],
        )
        with self.assertRaisesRegex(ValueError, "assignment digests span units"):
            validate_context_frontier_overlay(wrong_unit)

    def test_validator_rejects_noncanonical_hashes_and_numbers(self) -> None:
        plan = deepcopy(self.overlay)
        plan["plan_sha256"] = plan["plan_sha256"].upper()
        epoch = deepcopy(self.overlay)
        epoch["query_epoch"] = -1
        version = deepcopy(self.overlay)
        version["base_frontier"]["state_version"] = True
        for value in (plan, epoch, version):
            with self.assertRaises(ValueError):
                validate_context_frontier_overlay(value)

    def test_validator_rejects_non_repo_relative_references(self) -> None:
        for path in ("../refresh.json", "C:/refresh.json", "target\\refresh.json"):
            value = deepcopy(self.overlay)
            value["refresh_bundle"]["path"] = path
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    validate_context_frontier_overlay(value)

    def test_validator_recomputes_assignment_set_and_context_hashes(self) -> None:
        assignment_set = deepcopy(self.overlay)
        assignment_set["assignment_set_sha256"] = _sha("wrong-set")
        with self.assertRaisesRegex(ValueError, "assignment set SHA-256 drifted"):
            validate_context_frontier_overlay(assignment_set)

        context = deepcopy(self.overlay)
        context["effective_context"]["note"] = "tampered"
        with self.assertRaisesRegex(ValueError, "effective context SHA-256 drifted"):
            validate_context_frontier_overlay(context)

    def test_validator_cross_checks_effective_context_outputs(self) -> None:
        value = deepcopy(self.overlay)
        value["selection_receipt_sha256"] = _sha("other-receipt")
        with self.assertRaisesRegex(ValueError, "selection_receipt_sha256 drifted"):
            validate_context_frontier_overlay(value)

    def test_resolver_rejects_unbound_or_other_unit_assignments(self) -> None:
        frontier = self.frontier()
        changed = deepcopy(self.assignments[0])
        changed["immutable_input"]["new"] = True
        with self.assertRaisesRegex(ValueError, "digest is not allowed"):
            resolve_effective_context(changed, frontier, self.overlay)

        other = self.assignment("translator", unit_id="unit-b")
        with self.assertRaisesRegex(ValueError, "assignment unit binding drifted"):
            resolve_effective_context(other, frontier, self.overlay)

    def test_resolver_rejects_overlay_reference_identity_drift(self) -> None:
        frontier = self.frontier()
        frontier["context_overlay"]["sha256"] = _sha("wrong-overlay")
        with self.assertRaisesRegex(ValueError, "reference identity drifted"):
            resolve_effective_context(self.assignments[0], frontier, self.overlay)

        frontier = self.frontier()
        frontier["context_overlay"]["size_bytes"] += 1
        with self.assertRaisesRegex(ValueError, "reference identity drifted"):
            resolve_effective_context(self.assignments[0], frontier, self.overlay)

    def test_resolver_rejects_frontier_output_drift(self) -> None:
        frontier = self.frontier()
        frontier["materialized_page_set_sha256"] = _sha("wrong-pages")
        with self.assertRaisesRegex(ValueError, "frontier materialized_page_set_sha256 drifted"):
            resolve_effective_context(self.assignments[0], frontier, self.overlay)


if __name__ == "__main__":
    unittest.main()
