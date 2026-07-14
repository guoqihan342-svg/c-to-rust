from __future__ import annotations

from copy import deepcopy
import hashlib
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.context_frontier_wave import (
    build_context_expansion_query,
    derive_context_frontier_wave_input,
    validate_context_expansion_query,
)
from validation.tools._project_migration_harness.gate_authority import (
    candidate_verdict_payload,
)
from validation.tools._project_migration_harness.portfolio_integrity import (
    canonical_dag,
    canonical_group,
)


RUN_ID = "wave-input-run"
CLAIM_BOUNDARY = {"semantic_gate": False, "translation_coverage_numerator": 0}


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def group(group_id: str, dependencies: list[str]) -> dict[str, object]:
    raw = {
        "group_id": group_id,
        "dependencies": dependencies,
        "classification": "independent",
        "structurally_eligible": True,
        "context_pack": None,
    }
    payload, sha256 = canonical_group(raw, dependencies, None)
    return {**payload, "content_sha256": sha256}


def migration_dag() -> dict[str, object]:
    groups = [
        group("unit-a", []),
        group("unit-b", []),
        group("unit-c", ["unit-a", "unit-b"]),
        group("unit-d", ["unit-c"]),
    ]
    payload = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "project_key": "generic-project",
        "groups": groups,
        "waves": [
            {"wave_index": 0, "group_ids": ["unit-a", "unit-b"]},
            {"wave_index": 1, "group_ids": ["unit-c"]},
            {"wave_index": 2, "group_ids": ["unit-d"]},
        ],
        "claim_boundary": dict(CLAIM_BOUNDARY),
    }
    return {**payload, "dag_sha256": canonical_dag(payload, groups)}


def failure(
    sequence: int, *, unit_id: str = "unit-a", family: str = "compile",
    candidate: str | None = None,
) -> dict[str, object]:
    candidate_id = candidate or f"candidate-{sequence}"
    evidence = candidate_verdict_payload(
        run_id=RUN_ID,
        unit_id=unit_id,
        candidate_artifact_id=candidate_id,
        candidate_sha256=digest(candidate_id),
        gate_family=family,
        status="failed",
        diagnostics=[{"code": "compile-error", "stage": "compile"}],
    )
    return {
        "sequence": sequence,
        "sha256": content_sha256(evidence),
        "evidence": evidence,
    }


def query(epoch: int, failure_sha256: str) -> dict[str, object]:
    return build_context_expansion_query(
        run_id=RUN_ID,
        unit_id="unit-c",
        query_epoch=epoch,
        requests=[
            {"family": "include-adjacency", "anchor_fact_sha256": digest("include")},
            {"family": "dependency-scc-interface", "dependency_scc_id": "unit-a"},
            {"family": "verified-failure-fact",
             "failure_evidence_sha256": failure_sha256},
        ],
    )


def rebind_group(dag: dict, group_id: str) -> None:
    index = next(i for i, item in enumerate(dag["groups"]) if item["group_id"] == group_id)
    raw = dag["groups"][index]
    payload, sha256 = canonical_group(
        raw, raw["dependencies"], raw.get("context_pack"),
    )
    dag["groups"][index] = {**payload, "content_sha256": sha256}
    dag["dag_sha256"] = canonical_dag(dag, dag["groups"])


class ProjectMigrationContextFrontierWaveTests(unittest.TestCase):
    def test_derives_only_next_wave_from_latest_bound_inputs(self) -> None:
        old = failure(3)
        latest = failure(9)
        other = failure(5, unit_id="unit-b", family="negative")
        old_query = build_context_expansion_query(
            run_id=RUN_ID,
            unit_id="unit-c",
            query_epoch=1,
            requests=[{"family": "dependency-scc-interface",
                       "dependency_scc_id": "unit-b"}],
        )
        latest_query = query(2, latest["sha256"])

        result = derive_context_frontier_wave_input(
            migration_dag(),
            completed_wave_index=0,
            failure_evidence=[old, other, latest],
            expansion_queries=[old_query, latest_query],
        )

        self.assertEqual(1, result["next_wave_index"])
        self.assertEqual(["unit-c"], result["next_unit_ids"])
        self.assertEqual(
            [("unit-a", 9), ("unit-b", 5)],
            [(item["unit_id"], item["sequence"]) for item in result["failure_evidence"]],
        )
        unit = result["units"][0]
        self.assertEqual(
            sorted([latest["sha256"], other["sha256"]]),
            unit["failure_evidence_sha256s"],
        )
        self.assertEqual([latest_query["sha256"]], unit["expansion_query_sha256s"])
        self.assertEqual(CLAIM_BOUNDARY, result["claim_boundary"])
        payload = {key: value for key, value in result.items() if key != "sha256"}
        self.assertEqual(content_sha256(payload), result["sha256"])

    def test_input_order_is_deterministic_and_stale_entries_do_not_win(self) -> None:
        old = failure(1)
        latest = failure(2)
        old_query = build_context_expansion_query(
            run_id=RUN_ID, unit_id="unit-c", query_epoch=1,
            requests=[{"family": "include-adjacency",
                       "anchor_fact_sha256": digest("older-anchor")}],
        )
        latest_query = query(4, latest["sha256"])
        first = derive_context_frontier_wave_input(
            migration_dag(), completed_wave_index=0,
            failure_evidence=[old, latest],
            expansion_queries=[old_query, latest_query],
        )
        second = derive_context_frontier_wave_input(
            migration_dag(), completed_wave_index=0,
            failure_evidence=[latest, old],
            expansion_queries=[latest_query, old_query],
        )
        self.assertEqual(first, second)
        self.assertEqual([2], [item["sequence"] for item in first["failure_evidence"]])
        self.assertEqual(4, first["expansion_queries"][0]["query_epoch"])

    def test_empty_dynamic_inputs_remain_nonsemantic_and_content_bound(self) -> None:
        result = derive_context_frontier_wave_input(
            migration_dag(), completed_wave_index=0,
            failure_evidence=[], expansion_queries=[],
        )
        unit = result["units"][0]
        self.assertEqual(content_sha256([]), unit["failure_fact_set_sha256"])
        self.assertEqual(content_sha256([]), unit["expansion_query_set_sha256"])
        self.assertFalse(result["claim_boundary"]["semantic_gate"])
        self.assertEqual(0, result["claim_boundary"]["translation_coverage_numerator"])

    def test_dag_drift_future_edges_and_terminal_wave_fail_closed(self) -> None:
        drifted = migration_dag()
        drifted["project_key"] = "changed-project"
        with self.assertRaisesRegex(ValueError, "DAG SHA-256 drifted"):
            derive_context_frontier_wave_input(
                drifted, completed_wave_index=0,
                failure_evidence=[], expansion_queries=[],
            )

        future_edge = migration_dag()
        future_edge["groups"][2]["dependencies"] = ["unit-d"]
        rebind_group(future_edge, "unit-c")
        with self.assertRaisesRegex(ValueError, "earlier-wave edges"):
            derive_context_frontier_wave_input(
                future_edge, completed_wave_index=0,
                failure_evidence=[], expansion_queries=[],
            )

        with self.assertRaisesRegex(ValueError, "no next wave"):
            derive_context_frontier_wave_input(
                migration_dag(), completed_wave_index=2,
                failure_evidence=[], expansion_queries=[],
            )

    def test_failure_evidence_requires_host_verdict_hash_and_completed_scope(self) -> None:
        valid = failure(1)
        cases = {}
        drifted = deepcopy(valid)
        drifted["evidence"]["diagnostics"][0]["code"] = "changed-code"
        cases["SHA-256 drifted"] = [drifted]
        future = failure(2, unit_id="unit-d")
        cases["outside the completed"] = [future]
        passed = deepcopy(valid)
        passed["evidence"]["status"] = "passed"
        passed["sha256"] = content_sha256(passed["evidence"])
        cases["failed host verdict"] = [passed]
        duplicate = failure(1, unit_id="unit-b", family="negative")
        cases["sequence is duplicated"] = [valid, duplicate]
        for message, values in cases.items():
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    derive_context_frontier_wave_input(
                        migration_dag(), completed_wave_index=0,
                        failure_evidence=values, expansion_queries=[],
                    )

    def test_expansion_queries_are_hash_bound_and_frontier_scoped(self) -> None:
        evidence = failure(1)
        valid = query(1, evidence["sha256"])
        self.assertEqual(valid, validate_context_expansion_query(valid))

        drifted = deepcopy(valid)
        drifted["requests"][0]["dependency_scc_id"] = "unit-b"
        with self.assertRaisesRegex(ValueError, "binding drifted"):
            validate_context_expansion_query(drifted)

        invalid_requests = [
            ({"family": "dependency-scc-interface", "dependency_scc_id": "unit-d"},
             "non-direct dependency"),
            ({"family": "verified-failure-fact",
              "failure_evidence_sha256": digest("unrelated")},
             "unrelated failure"),
        ]
        for request, message in invalid_requests:
            with self.subTest(message=message):
                invalid = build_context_expansion_query(
                    run_id=RUN_ID, unit_id="unit-c", query_epoch=3,
                    requests=[request],
                )
                with self.assertRaisesRegex(ValueError, message):
                    derive_context_frontier_wave_input(
                        migration_dag(), completed_wave_index=0,
                        failure_evidence=[evidence], expansion_queries=[invalid],
                    )

        outside = build_context_expansion_query(
            run_id=RUN_ID, unit_id="unit-d", query_epoch=1,
            requests=[{"family": "include-adjacency",
                       "anchor_fact_sha256": digest("anchor")}],
        )
        with self.assertRaisesRegex(ValueError, "outside the next DAG wave"):
            derive_context_frontier_wave_input(
                migration_dag(), completed_wave_index=0,
                failure_evidence=[evidence], expansion_queries=[outside],
            )

    def test_query_builder_rejects_unbounded_or_ambiguous_requests(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one request"):
            build_context_expansion_query(
                run_id=RUN_ID, unit_id="unit-c", query_epoch=0, requests=[],
            )
        request = {"family": "include-adjacency", "anchor_fact_sha256": digest("same")}
        with self.assertRaisesRegex(ValueError, "duplicated"):
            build_context_expansion_query(
                run_id=RUN_ID, unit_id="unit-c", query_epoch=0,
                requests=[request, request],
            )
        with self.assertRaisesRegex(ValueError, "shape or family"):
            build_context_expansion_query(
                run_id=RUN_ID, unit_id="unit-c", query_epoch=0,
                requests=[{"family": "repository-wide", "path": "src"}],
            )


if __name__ == "__main__":
    unittest.main()
