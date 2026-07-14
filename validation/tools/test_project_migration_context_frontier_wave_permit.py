from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import (
    canonical_json_bytes,
    content_sha256,
)
from validation.tools._project_migration_harness.context_frontier_cas import (
    write_frontier_cas_json,
)
from validation.tools._project_migration_harness.context_frontier_state import (
    ContextFrontierProjection,
    validate_context_frontier_head,
)
from validation.tools._project_migration_harness.context_frontier_wave import (
    WAVE_INPUT_POLICY,
)
from validation.tools._project_migration_harness.context_frontier_wave_permit import (
    _HostContextFrontierWavePermit,
    _host_context_frontier_wave_binding,
    _issue_host_context_frontier_wave_permit,
    _reopen_host_context_frontier_wave_permit,
)


CLAIM_BOUNDARY = {"semantic_gate": False, "translation_coverage_numerator": 0}
MODULE = Path(__file__).parent / "_project_migration_harness" / "context_frontier_wave_permit.py"

class ProjectMigrationContextFrontierWavePermitTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="frontier-wave-permit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.wave = wave_input()
        self.reference = write_frontier_cas_json(
            self.root, "context-frontier-wave-input", self.wave,
        )
        self.current = ready_projection()
    def issue(self):
        return _issue_host_context_frontier_wave_permit(
            self.wave, self.reference, self.current,
        )
    def test_reopen_builds_content_bound_pending_head(self) -> None:
        permit = self.issue()

        reopened = _reopen_host_context_frontier_wave_permit(
            permit, harness_root=self.root, current_projection=self.current,
        )
        target = validate_context_frontier_head(reopened["target_head"])
        unit = self.wave["units"][0]

        self.assertEqual(("ready", 4, self.current.head_sha256), (
            reopened["expected_status"], reopened["expected_version"],
            reopened["expected_head_sha256"],
        ))
        self.assertEqual(("pending_retrieval", 8), (
            target["status"], target["query_epoch"],
        ))
        self.assertEqual(unit["dag_sha256"], target["input_binding"]["dag_sha256"])
        self.assertEqual(unit["group_sha256"], target["input_binding"]["group_sha256"])
        self.assertEqual(
            unit["failure_fact_set_sha256"],
            target["input_binding"]["failure_fact_set_sha256"],
        )
        self.assertEqual(
            unit["selection_seed_sha256"],
            target["input_binding"]["selection_seed_sha256"],
        )
        self.assertEqual(self.current.head["input_binding"]["limits"], reopened["limits"])
        self.assertIsNone(target["context_overlay"])
        self.assertIsNone(target["selection_receipt_sha256"])
        self.assertEqual(self.reference, reopened["wave_input"])
    def test_replay_is_deterministic_and_old_permit_becomes_stale(self) -> None:
        first = self.issue()
        second = self.issue()
        self.assertEqual(
            _host_context_frontier_wave_binding(first),
            _host_context_frontier_wave_binding(second),
        )
        reopened = _reopen_host_context_frontier_wave_permit(
            first, harness_root=self.root, current_projection=self.current,
        )
        replay = _reopen_host_context_frontier_wave_permit(
            first, harness_root=self.root, current_projection=self.current,
        )
        self.assertEqual(reopened, replay)

        stale = ContextFrontierProjection(
            self.current.status, self.current.version + 1,
            self.current.head, self.current.head_sha256,
        )
        with self.assertRaisesRegex(ValueError, "stale or identity-drifted"):
            _reopen_host_context_frontier_wave_permit(
                first, harness_root=self.root, current_projection=stale,
            )
    def test_exact_type_and_binding_tamper_fail_closed(self) -> None:
        with self.assertRaisesRegex(TypeError, "host-issued"):
            _HostContextFrontierWavePermit(object(), {})
        with self.assertRaisesRegex(TypeError, "not host-issued"):
            _host_context_frontier_wave_binding(object())  # type: ignore[arg-type]

        permit = self.issue()
        permit._binding["dag_sha256"] = digest("tampered-dag")
        with self.assertRaisesRegex(ValueError, "binding drifted"):
            _reopen_host_context_frontier_wave_permit(
                permit, harness_root=self.root, current_projection=self.current,
            )
    def test_wave_artifact_and_logical_input_tamper_fail_closed(self) -> None:
        target = self.root.joinpath(*Path(self.reference["path"]).parts)
        target.write_bytes(canonical_json_bytes({**self.wave, "project_key": "changed"}))
        with self.assertRaisesRegex(ValueError, "SHA-256 drifted"):
            _reopen_host_context_frontier_wave_permit(
                self.issue(), harness_root=self.root,
                current_projection=self.current,
            )

        changed = deepcopy(self.wave)
        changed["units"][0]["group_sha256"] = digest("changed-group")
        with self.assertRaisesRegex(ValueError, "selection seed drifted|SHA-256 drifted"):
            _issue_host_context_frontier_wave_permit(
                changed, self.reference, self.current,
            )
    def test_identity_mismatch_and_non_ready_projection_are_rejected(self) -> None:
        wrong_run = deepcopy(self.wave)
        wrong_run["run_id"] = "another-run"
        wrong_run["units"][0]["run_id"] = "another-run"
        wrong_run["units"][0]["selection_seed_sha256"] = content_sha256({
            key: wrong_run["units"][0][key] for key in seed_keys()
        })
        wrong_run = rehash_wave(wrong_run)
        wrong_reference = write_frontier_cas_json(
            self.root, "context-frontier-wave-input", wrong_run,
        )
        with self.assertRaisesRegex(ValueError, "run identity"):
            _issue_host_context_frontier_wave_permit(
                wrong_run, wrong_reference, self.current,
            )

        pending_head = {
            **self.current.head,
            "status": "pending_retrieval",
            "context_overlay": None,
            "selection_receipt_sha256": None,
            "materialized_page_set_sha256": None,
            "selection_materialization_sha256": None,
        }
        pending = projection(pending_head, version=5)
        with self.assertRaisesRegex(ValueError, "bound ready"):
            _issue_host_context_frontier_wave_permit(
                self.wave, self.reference, pending,
            )

        outside = deepcopy(self.wave)
        outside["next_unit_ids"] = ["unit-b"]
        outside["units"][0]["unit_id"] = "unit-b"
        outside["units"][0]["selection_seed_sha256"] = content_sha256({
            key: outside["units"][0][key] for key in seed_keys()
        })
        outside = rehash_wave(outside)
        outside_reference = write_frontier_cas_json(
            self.root, "context-frontier-wave-input", outside,
        )
        with self.assertRaisesRegex(ValueError, "outside the next wave"):
            _issue_host_context_frontier_wave_permit(
                outside, outside_reference, self.current,
            )
    def test_claim_boundary_stays_nonsemantic_and_module_has_no_command_path(self) -> None:
        binding = _host_context_frontier_wave_binding(self.issue())
        self.assertEqual(CLAIM_BOUNDARY, binding["claim_boundary"])
        self.assertFalse(binding["claim_boundary"]["semantic_gate"])
        self.assertEqual(0, binding["claim_boundary"]["translation_coverage_numerator"])

        tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
        forbidden = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                forbidden.extend(
                    alias.name for alias in node.names
                    if alias.name.lstrip("_") == "ContextFrontierCommand"
                )
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else None
                if name is not None and name.lstrip("_") == "ContextFrontierCommand":
                    forbidden.append(name)
        self.assertEqual([], forbidden)

def ready_projection() -> ContextFrontierProjection:
    limits = {
        "context_byte_budget": 8192,
        "context_page_limit": 16,
        "context_token_budget": 4096,
    }
    input_binding = {
        "dag_sha256": digest("old-dag"),
        "group_sha256": digest("old-group"),
        "failure_fact_set_sha256": content_sha256([]),
        "selection_seed_sha256": digest("old-seed"),
        "limits": limits,
    }
    head = {
        "schema_version": 2,
        "run_id": "wave-permit-run",
        "unit_id": "unit-c",
        "status": "ready",
        "mode": "host_retrieval",
        "query_epoch": 7,
        "input_binding": input_binding,
        "selection_input_sha256": content_sha256(input_binding),
        "catalog": reference("catalog"),
        "context_overlay": reference("overlay"),
        "selection_receipt_sha256": digest("receipt"),
        "materialized_page_set_sha256": digest("pages"),
        "selection_materialization_sha256": digest("materialization"),
    }
    return projection(head, version=4)

def wave_input() -> dict:
    failures: list[dict] = []
    queries: list[dict] = []
    seed = {
        "policy": WAVE_INPUT_POLICY,
        "run_id": "wave-permit-run",
        "unit_id": "unit-c",
        "wave_index": 1,
        "dag_sha256": digest("new-dag"),
        "group_sha256": digest("unit-c-group"),
        "dependency_closure_sha256": content_sha256(["unit-a"]),
        "failure_fact_set_sha256": content_sha256([]),
        "expansion_query_set_sha256": content_sha256([]),
    }
    unit = {
        **seed,
        "selection_seed_sha256": content_sha256(seed),
        "failure_evidence_sha256s": [],
        "expansion_query_sha256s": [],
    }
    payload = {
        "schema_version": 1,
        "artifact_kind": "context-frontier-wave-input",
        "policy": WAVE_INPUT_POLICY,
        "run_id": "wave-permit-run",
        "project_key": "portable-c-project",
        "completed_wave_index": 0,
        "next_wave_index": 1,
        "dag_sha256": seed["dag_sha256"],
        "next_unit_ids": ["unit-c"],
        "failure_evidence": failures,
        "failure_evidence_set_sha256": content_sha256(failures),
        "expansion_queries": queries,
        "expansion_query_set_sha256": content_sha256(queries),
        "units": [unit],
        "claim_boundary": dict(CLAIM_BOUNDARY),
    }
    return {**payload, "sha256": content_sha256(payload)}


def rehash_wave(value: dict) -> dict:
    payload = {key: item for key, item in value.items() if key != "sha256"}
    return {**payload, "sha256": content_sha256(payload)}


def projection(head: dict, *, version: int) -> ContextFrontierProjection:
    normalized = validate_context_frontier_head(head)
    return ContextFrontierProjection(
        normalized["status"], version, normalized, content_sha256(normalized),
    )


def reference(label: str) -> dict:
    return {
        "path": f"context/{label}.json",
        "sha256": digest(label),
        "size_bytes": len(label),
    }


def seed_keys() -> tuple[str, ...]:
    return (
        "policy", "run_id", "unit_id", "wave_index", "dag_sha256",
        "group_sha256", "dependency_closure_sha256",
        "failure_fact_set_sha256", "expansion_query_set_sha256",
    )


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    unittest.main()
