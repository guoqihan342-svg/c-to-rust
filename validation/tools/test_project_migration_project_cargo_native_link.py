from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from validation.tools._project_migration_harness.project_cargo_native_link import (
    settle_cargo_native_links,
)
from validation.tools._project_migration_harness.project_native_link_settlement_binding import (
    project_native_link_settlement_status,
)


MODULE = (
    "validation.tools._project_migration_harness.project_cargo_native_link"
)


class ProjectCargoNativeLinkTests(unittest.TestCase):
    def test_no_native_requirements_needs_no_manifest_or_trace(self) -> None:
        result = settle_cargo_native_links(
            **_inputs({"native_link_requirements": []}),
        )
        self.assertEqual("not-required", result["status"])
        self.assertEqual(0, result["requirement_count"])

    def test_required_native_link_without_manifest_fails_closed(self) -> None:
        result = settle_cargo_native_links(
            **_inputs({"native_link_requirements": [_requirement()]}),
        )
        self.assertEqual("blocked", result["status"])
        self.assertEqual("native_link_manifest_unavailable", result["reason_code"])
        self.assertEqual(1, result["requirement_count"])

    def test_recovered_state_is_forwarded_to_evidence_settlement(self) -> None:
        context = {"context_sha256": "a" * 64, "requirement_count": 1}
        state = {"status": "candidate-missing", "context": context,
                 "candidate": None}
        expected = project_native_link_settlement_status(
            "blocked", context=context,
            reason_code="native_link_candidate_missing",
        )
        with (
            mock.patch(f"{MODULE}.recover_project_native_link_state",
                       return_value=state) as recover,
            mock.patch(f"{MODULE}.settle_project_native_links",
                       return_value=expected) as settle,
        ):
            result = settle_cargo_native_links(
                **_inputs(
                    {"native_link_requirements": [_requirement()]},
                    migration_manifest={"profile": "competition"},
                ),
            )
        self.assertEqual(expected, result)
        recover.assert_called_once()
        settle.assert_called_once()

    def test_evidence_failure_does_not_escape_or_claim_resolution(self) -> None:
        context = {"context_sha256": "a" * 64, "requirement_count": 1}
        candidate = {"candidate_sha256": "b" * 64}
        state = {"status": "candidate-ready", "context": context,
                 "candidate": candidate}
        with (
            mock.patch(f"{MODULE}.recover_project_native_link_state",
                       return_value=state),
            mock.patch(f"{MODULE}.settle_project_native_links",
                       side_effect=ValueError("tampered")),
        ):
            result = settle_cargo_native_links(
                **_inputs(
                    {"native_link_requirements": [_requirement()]},
                    migration_manifest={"profile": "competition"},
                ),
            )
        self.assertEqual("blocked", result["status"])
        self.assertEqual(
            "native_link_settlement_evidence_unavailable", result["reason_code"],
        )
        self.assertFalse(result["resolution_gate"])


def _inputs(ir: dict, migration_manifest: dict | None = None) -> dict:
    return {
        "ledger_path": Path("state/ledger.sqlite3"),
        "out_root": Path("target/run"),
        "context": {"rust_project_ir": ir},
        "migration_manifest": migration_manifest,
        "execution": {}, "checks": {}, "observations": {},
    }


def _requirement() -> dict:
    return {"requirement_id": "native-1"}


if __name__ == "__main__":
    unittest.main()
