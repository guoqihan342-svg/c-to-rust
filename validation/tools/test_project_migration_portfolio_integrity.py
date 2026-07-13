from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from validation.tools._project_migration_harness.artifacts import canonical_json_bytes
from validation.tools._project_migration_harness.portfolio import PortfolioError, plan_portfolio
from validation.tools._project_migration_harness.portfolio_integrity import canonical_sha256


def page(path: str, label: str) -> tuple[dict[str, object], bytes]:
    payload = canonical_json_bytes({"label": label, "facts": [label]})
    return ({
        "path": path,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "byte_count": len(payload),
        "token_count": len(payload),
    }, payload)


def context(group_id: str, page_binding: dict[str, object], payload: bytes) -> dict[str, object]:
    return {
        "path": f"target/run/context/groups/{group_id}.json",
        "sha256": "f" * 64,
        "byte_count": len(payload),
        "token_count": len(payload),
        "page_count": 1,
        "pages": [page_binding],
    }


def group(
    group_id: str,
    context_pack: dict[str, object] | None,
    *,
    dependencies: list[str] | None = None,
    eligible: bool = True,
) -> dict[str, object]:
    return {
        "group_id": group_id,
        "structurally_eligible": eligible,
        "dependencies": dependencies or [],
        "context_pack": context_pack,
        "content_sha256": "e" * 64,
    }


def plan(
    dag: dict[str, object],
    payloads: dict[str, bytes] | None,
    *,
    max_concurrency: int = 2,
    page_root: Path | None = None,
) -> dict[str, object]:
    return plan_portfolio(
        dag,
        out_root="target/run",
        max_concurrency=max_concurrency,
        max_attempts=3,
        context_byte_budget=4_096,
        context_token_budget=4_096,
        context_page_payloads=payloads,
        context_page_root=page_root,
    )


class PortfolioIntegrityTests(unittest.TestCase):
    def test_waves_must_partition_groups_and_dependencies_must_exist(self) -> None:
        binding, payload = page("target/run/context/pages/one.json", "one")
        one = group("one", context("one", binding, payload))
        omitted = {
            "run_id": "run",
            "project_key": "project",
            "groups": [one],
            "waves": [{"wave_index": 0, "group_ids": []}],
        }
        with self.assertRaisesRegex(PortfolioError, "waves omit groups: one"):
            plan(omitted, {binding["path"]: payload})

        one["dependencies"] = ["missing"]
        complete = {**omitted, "waves": [{"wave_index": 0, "group_ids": ["one"]}]}
        with self.assertRaisesRegex(PortfolioError, "unknown dependencies: missing"):
            plan(complete, {binding["path"]: payload})

    def test_structurally_blocked_dependencies_propagate(self) -> None:
        blocked_page, blocked_payload = page("target/run/context/pages/blocked.json", "blocked")
        child_page, child_payload = page("target/run/context/pages/child.json", "child")
        dag = {
            "run_id": "run",
            "project_key": "project",
            "groups": [
                group("blocked", context("blocked", blocked_page, blocked_payload), eligible=False),
                group(
                    "child",
                    context("child", child_page, child_payload),
                    dependencies=["blocked"],
                ),
            ],
            "waves": [
                {"wave_index": 0, "group_ids": ["blocked"]},
                {"wave_index": 1, "group_ids": ["child"]},
            ],
        }
        result = plan(dag, {
            blocked_page["path"]: blocked_payload,
            child_page["path"]: child_payload,
        })

        reasons = {item["group_id"]: item["reasons"] for item in result["blocked_groups"]}
        self.assertIn("structural_eligibility_not_proven", reasons["blocked"])
        self.assertIn("dependency_blocked:blocked", reasons["child"])
        self.assertEqual(result["assignments"], [])
        ledger_status = {
            item["group_id"]: (item["status"], item["resumable_status"])
            for item in result["ledger_units"]
        }
        self.assertEqual(ledger_status["blocked"], ("blocked", "terminal"))
        self.assertEqual(ledger_status["child"], ("blocked", "terminal"))

    def test_boundary_group_is_planned_before_translation(self) -> None:
        binding, payload = page("target/run/context/pages/boundary.json", "boundary")
        boundary = group("boundary", context("boundary", binding, payload), eligible=False)
        boundary["classification"] = "boundary_required"
        dag = {
            "run_id": "run",
            "project_key": "project",
            "groups": [boundary],
            "waves": [{"wave_index": 0, "group_ids": ["boundary"]}],
        }
        result = plan(dag, {binding["path"]: payload})
        assignments = {item["role"]: item for item in result["assignments"]}

        self.assertEqual(
            set(assignments), {"planner", "translator", "reviewer", "repairer"},
        )
        planner = assignments["planner"]
        self.assertEqual(planner["launch_policy"]["state"], "ready")
        self.assertFalse(planner["authority"]["semantic_acceptance"])
        self.assertEqual(planner["authority"]["planning_scope"], "structural-route-only")
        self.assertEqual(
            set(planner["planner_decision_contract"]["allowed_decisions"]),
            {"translate_with_context", "preserve_ffi_boundary", "refuse_with_reason"},
        )
        self.assertTrue(planner["planner_decision_contract"]["sha256_required"])
        self.assertEqual(
            planner["planner_decision_contract"]["hash_payload_fields"],
            ["run_id", "group_id", "group_sha256", "context_pack_sha256", "decision"],
        )
        self.assertEqual(planner["ledger_binding"]["role"], "planner")

        translator = assignments["translator"]
        policy = translator["launch_policy"]
        self.assertFalse(translator["authority"]["semantic_acceptance"])
        self.assertEqual(policy["state"], "deferred")
        self.assertIn("planner_decision_sha256", policy["requires"])
        self.assertEqual(policy["planner_decision"]["hash_algorithm"], "sha256")
        self.assertEqual(policy["planner_decision"]["translate_when"], "translate_with_context")
        self.assertEqual(
            set(policy["planner_decision"]["terminal_decisions"]),
            {"preserve_ffi_boundary", "refuse_with_reason"},
        )
        self.assertEqual([item["role"] for item in result["units"]], ["planner"])
        self.assertEqual(result["blocked_groups"], [])

    def test_hashes_and_page_counts_are_recomputed_from_payload(self) -> None:
        binding, payload = page("target/run/context/pages/one.json", "one")
        dag = {
            "run_id": "run",
            "project_key": "project",
            "dag_sha256": "d" * 64,
            "groups": [group("one", context("one", binding, payload))],
            "waves": [{"wave_index": 0, "group_ids": ["one"]}],
        }
        result = plan(dag, {binding["path"]: payload})
        assignment = result["assignments"][0]
        bound_context = assignment["context"]

        self.assertNotEqual(result["dag_sha256"], "d" * 64)
        self.assertNotEqual(assignment["group_sha256"], "e" * 64)
        self.assertEqual(result["ledger_units"][0]["content_sha256"], assignment["group_sha256"])
        self.assertNotEqual(bound_context["sha256"], "f" * 64)
        self.assertEqual(bound_context["pages"][0]["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(bound_context["pages"][0]["byte_count"], len(payload))
        self.assertEqual(bound_context["pages"][0]["token_count"], len(payload))

        dag["dag_sha256"] = "a" * 64
        dag["groups"][0]["content_sha256"] = "b" * 64
        dag["groups"][0]["context_pack"]["sha256"] = "c" * 64
        repeated = plan(dag, {binding["path"]: payload})
        self.assertEqual(result, repeated)

    def test_page_payload_is_required_and_claimed_binding_must_match(self) -> None:
        binding, payload = page("target/run/context/pages/one.json", "one")
        dag = {
            "run_id": "run",
            "project_key": "project",
            "groups": [group("one", context("one", binding, payload))],
            "waves": [{"wave_index": 0, "group_ids": ["one"]}],
        }
        with self.assertRaisesRegex(PortfolioError, "page payload is unavailable"):
            plan(dag, None)

        with self.assertRaisesRegex(PortfolioError, "sha256 does not match"):
            plan(dag, {binding["path"]: b"different"})

        dag["groups"][0]["context_pack"]["byte_count"] = len(payload) + 1
        with self.assertRaisesRegex(PortfolioError, "byte_count does not match"):
            plan(dag, {binding["path"]: payload})

    def test_context_page_can_be_verified_from_disk(self) -> None:
        relative = "target/run/context/pages/one.json"
        binding, payload = page(relative, "one")
        dag = {
            "run_id": "run",
            "project_key": "project",
            "groups": [group("one", context("one", binding, payload))],
            "waves": [{"wave_index": 0, "group_ids": ["one"]}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / Path(*relative.split("/"))
            target.parent.mkdir(parents=True)
            target.write_bytes(payload)
            result = plan(dag, None, page_root=root)
        self.assertEqual(result["assignments"][0]["context"]["pages"][0]["byte_count"], len(payload))

    def test_initial_units_respect_concurrency_and_ledger_binding_is_explicit(self) -> None:
        one_page, one_payload = page("target/run/context/pages/one.json", "one")
        two_page, two_payload = page("target/run/context/pages/two.json", "two")
        dag = {
            "run_id": "run",
            "project_key": "project",
            "groups": [
                group("one", context("one", one_page, one_payload)),
                group("two", context("two", two_page, two_payload)),
            ],
            "waves": [{"wave_index": 0, "group_ids": ["one", "two"]}],
        }
        result = plan(dag, {
            one_page["path"]: one_payload,
            two_page["path"]: two_payload,
        }, max_concurrency=1)

        self.assertEqual(len(result["units"]), 1)
        self.assertEqual(len(result["initial_ready"]["deferred_worker_ids"]), 1)
        assignment = result["assignments"][0]
        ledger = assignment["ledger_binding"]
        self.assertEqual(ledger["unit_id"], assignment["group_id"])
        self.assertEqual(ledger["role"], assignment["role"])
        self.assertEqual(ledger["worker_id"], assignment["worker_id"])
        self.assertEqual(ledger["lease_owner"], assignment["worker_identity"])
        self.assertEqual(ledger["isolated_out_root"], assignment["isolated_out_root"])
        expected = canonical_sha256({key: value for key, value in ledger.items() if key != "binding_sha256"})
        self.assertEqual(ledger["binding_sha256"], expected)

    def test_repair_modes_do_not_require_last_good_for_first_candidate(self) -> None:
        binding, payload = page("target/run/context/pages/one.json", "one")
        dag = {
            "run_id": "run",
            "project_key": "project",
            "groups": [group("one", context("one", binding, payload))],
            "waves": [{"wave_index": 0, "group_ids": ["one"]}],
        }
        result = plan(dag, {binding["path"]: payload})
        repair = next(item for item in result["assignments"] if item["role"] == "repairer")
        policy = repair["launch_policy"]
        modes = {item["mode"]: item for item in policy["repair_modes"]}

        self.assertNotIn("last_good_artifact_id", policy["requires"])
        self.assertFalse(modes["candidate_repair"]["last_good_required"])
        self.assertNotIn("last_good_artifact_id", modes["candidate_repair"]["requires"])
        self.assertTrue(modes["post_last_good_regression_repair"]["last_good_required"])
        self.assertIn("last_good_artifact_id", modes["post_last_good_regression_repair"]["requires"])
        self.assertFalse(result["execution"]["direct_run_plan_safe"])
        self.assertNotIn("run_plan_compatible_fields", repair)


if __name__ == "__main__":
    unittest.main()
