from __future__ import annotations

import hashlib
import unittest
from typing import Any

from validation.tools._project_migration_harness.artifacts import canonical_json_bytes
from validation.tools._project_migration_harness.portfolio import plan_portfolio


_ABSENT = object()


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
        result = _plan({
            "selection_status": "ready",
            "selection_receipt_sha256": "a" * 64,
            "selection_blockers": [],
        })

        self.assertTrue(result["assignments"])
        self.assertEqual(result["blocked_groups"], [])

    def test_context_without_retrieval_contract_remains_assignable(self) -> None:
        result = _plan()

        self.assertTrue(result["assignments"])
        self.assertEqual(result["blocked_groups"], [])

    def test_non_ready_retrieval_contract_never_creates_assignments(self) -> None:
        valid_receipt = "b" * 64
        cases = {
            "blocked_status": {
                "selection_status": "blocked",
                "selection_receipt_sha256": valid_receipt,
                "selection_blockers": [],
            },
            "selection_blockers": {
                "selection_status": "ready",
                "selection_receipt_sha256": valid_receipt,
                "selection_blockers": ["selection_budget_exceeded"],
            },
            "tampered_receipt": {
                "selection_status": "ready",
                "selection_receipt_sha256": "b" * 63 + "x",
                "selection_blockers": [],
            },
            "missing_receipt": {
                "selection_status": "ready",
                "selection_blockers": [],
            },
        }

        for label, retrieval in cases.items():
            with self.subTest(label=label):
                result = _plan(retrieval)
                self.assertEqual(result["assignments"], [])
                self.assertEqual(result["units"], [])
                self.assertEqual(result["waves"][0]["worker_ids"], [])
                self.assertEqual(result["blocked_groups"], [{
                    "group_id": "neutral-group",
                    "wave_index": 0,
                    "reasons": ["context_retrieval_not_ready"],
                }])
                self.assertEqual(result["ledger_units"][0]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
