from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.project_native_link_settlement_binding import (
    project_native_link_settlement_status,
    validate_project_native_link_settlement_binding,
)


class ProjectNativeLinkSettlementBindingTests(unittest.TestCase):
    def test_not_required_and_candidate_missing_are_explicit(self) -> None:
        not_required = project_native_link_settlement_status(
            "not-required", context=_context(0),
        )
        self.assertEqual("not-required", not_required["status"])
        self.assertFalse(not_required["resolution_gate"])

        missing = project_native_link_settlement_status(
            "blocked", context=_context(1),
            reason_code="native_link_candidate_missing",
        )
        self.assertEqual("blocked", missing["status"])
        self.assertEqual(1, missing["requirement_count"])
        self.assertEqual({}, missing["artifacts"])

    def test_full_resolved_binding_requires_content_addressed_artifacts(self) -> None:
        binding = project_native_link_settlement_status(
            "resolved", context=_context(1), candidate=_candidate(),
            artifacts=_artifacts(), settlement_receipt_sha256="c" * 64,
            resolution_gate=True,
        )
        self.assertEqual("resolved", binding["status"])
        self.assertTrue(binding["resolution_gate"])
        self.assertEqual(8, len(binding["artifacts"]))

    def test_tampered_gate_or_reference_fails_closed(self) -> None:
        binding = project_native_link_settlement_status(
            "resolved", context=_context(1), candidate=_candidate(),
            artifacts=_artifacts(), settlement_receipt_sha256="c" * 64,
            resolution_gate=True,
        )
        tampered = copy.deepcopy(binding)
        tampered["resolution_gate"] = False
        tampered["binding_sha256"] = _binding_sha(tampered)
        with self.assertRaisesRegex(ValueError, "settlement_state_invalid"):
            validate_project_native_link_settlement_binding(tampered)

        bad_reference = copy.deepcopy(binding)
        bad_reference["artifacts"]["trace"]["path"] = "trace.json"
        bad_reference["binding_sha256"] = _binding_sha(bad_reference)
        with self.assertRaisesRegex(ValueError, "settlement_reference_invalid"):
            validate_project_native_link_settlement_binding(bad_reference)


def _context(requirement_count: int) -> dict:
    return {
        "context_sha256": "a" * 64,
        "requirement_count": requirement_count,
    }


def _candidate() -> dict:
    return {"candidate_sha256": "b" * 64}


def _reference(scope: str) -> dict:
    digest = content_sha256(scope)
    return {
        "path": f"verification/{scope}/{digest}.json",
        "sha256": digest,
        "size_bytes": 2,
    }


def _artifacts() -> dict:
    keys = (
        "trace", "actual_resolution", "order_evidence", "abi_evidence",
        "symbol_context", "symbol_evidence", "settlement",
    )
    return {
        **{key: _reference(key.replace("_", "-")) for key in keys},
        "symbol_candidate": None,
    }


def _binding_sha(value: dict) -> str:
    return content_sha256({
        key: item for key, item in value.items() if key != "binding_sha256"
    })


if __name__ == "__main__":
    unittest.main()
