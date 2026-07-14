from __future__ import annotations

import hashlib
import unittest
from typing import Any

from validation.tools._project_migration_harness.artifacts import canonical_json_bytes
from validation.tools._project_migration_harness.portfolio import plan_portfolio
from validation.tools._project_migration_harness.scheduler import schedule_portfolio


_ABSENT = object()


def _ready_retrieval(**updates: Any) -> dict[str, Any]:
    value = {
        "selection_status": "ready",
        "selection_receipt_sha256": "a" * 64,
        "selection_blockers": [],
        "required_fact_query_policy": "host-required-symbol-facts-v1",
        "required_fact_query_sha256": "b" * 64,
        "required_fact_query_count": 1,
        "required_fact_match_count": 1,
        "required_fact_match_set_sha256": "c" * 64,
        "unresolved_required_fact_count": 0,
        "unresolved_required_fact_set_sha256": "d" * 64,
    }
    value.update(updates)
    return value


def _plan(retrieval: Any = _ABSENT) -> dict[str, Any]:
    page_path = "target/neutral/context/pages/group.json"
    page_payload = canonical_json_bytes({"facts": ["neutral"]})
    context: dict[str, Any] = {
        "path": "target/neutral/context/groups/group.json",
        "byte_count": len(page_payload),
        "token_count": len(page_payload),
        "page_count": 1,
        "pages": [{
            "path": page_path,
            "sha256": hashlib.sha256(page_payload).hexdigest(),
            "byte_count": len(page_payload),
            "token_count": len(page_payload),
        }],
    }
    if retrieval is not _ABSENT:
        context["retrieval"] = retrieval
    dag = {
        "run_id": "neutral-run",
        "project_key": "neutral-project",
        "groups": [{
            "group_id": "neutral-group",
            "structurally_eligible": True,
            "dependencies": [],
            "context_pack": context,
        }],
        "waves": [{"wave_index": 0, "group_ids": ["neutral-group"]}],
    }
    return plan_portfolio(
        dag,
        out_root="target/neutral",
        max_concurrency=4,
        max_attempts=2,
        context_byte_budget=4_096,
        context_token_budget=4_096,
        context_page_payloads={page_path: page_payload},
    )


class RetrievalAdmissionTests(unittest.TestCase):
    def test_ready_retrieval_contract_is_assignable(self) -> None:
        result = _plan(_ready_retrieval())

        self.assertTrue(result["assignments"])
        self.assertEqual(result["blocked_groups"], [])
        self.assertEqual(result["pending_retrieval_groups"], [])

    def test_context_without_retrieval_contract_remains_assignable(self) -> None:
        result = _plan()

        self.assertTrue(result["assignments"])
        self.assertEqual(result["blocked_groups"], [])
        self.assertEqual(result["pending_retrieval_groups"], [])

    def test_non_ready_retrieval_contract_is_assignable_but_never_schedulable(self) -> None:
        valid_receipt = "b" * 64
        cases = {
            "blocked_status": _ready_retrieval(
                selection_status="blocked", selection_receipt_sha256=valid_receipt,
            ),
            "selection_blockers": _ready_retrieval(
                selection_receipt_sha256=valid_receipt,
                selection_blockers=["selection_budget_exceeded"],
            ),
            "tampered_receipt": _ready_retrieval(
                selection_receipt_sha256="b" * 63 + "x",
            ),
            "missing_receipt": {
                key: value for key, value in _ready_retrieval().items()
                if key != "selection_receipt_sha256"
            },
            "missing_required_fact_contract": {
                "selection_status": "ready",
                "selection_receipt_sha256": valid_receipt,
                "selection_blockers": [],
            },
            "unresolved_required_fact": _ready_retrieval(
                required_fact_match_count=0,
                unresolved_required_fact_count=1,
            ),
            "required_fact_hash_drift": _ready_retrieval(
                required_fact_match_set_sha256="c" * 63 + "x",
            ),
        }

        for label, retrieval in cases.items():
            with self.subTest(label=label):
                result = _plan(retrieval)
                self.assertEqual(len(result["assignments"]), 3)
                self.assertEqual(result["units"], [])
                self.assertEqual(len(result["waves"][0]["worker_ids"]), 3)
                self.assertEqual(result["blocked_groups"], [])
                self.assertEqual(result["pending_retrieval_groups"], [{
                    "group_id": "neutral-group",
                    "wave_index": 0,
                    "reasons": ["context_retrieval_not_ready"],
                }])
                self.assertEqual(
                    (result["ledger_units"][0]["status"],
                     result["ledger_units"][0]["resumable_status"]),
                    ("pending", "ready"),
                )
                self.assertEqual(
                    len(result["initial_ready"]["pending_retrieval_worker_ids"]), 3,
                )
                schedule = schedule_portfolio(result, result["ledger_units"], {})
                self.assertEqual(schedule["ready"], [])
                self.assertEqual(len(schedule["deferred"]), 3)
                self.assertTrue(all(
                    item["reasons"] == ["context_retrieval_pending"]
                    for item in schedule["deferred"]
                ))


if __name__ == "__main__":
    unittest.main()
