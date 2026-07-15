from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import unittest
from unittest import mock

from validation.tools._project_migration_harness.artifacts import canonical_json_bytes
from validation.tools._project_migration_harness.candidate_final_verifier import (
    verify_candidate_final,
)
from validation.tools._project_migration_harness.candidate_semantic_evidence import (
    current_semantic_context,
)
from validation.tools._project_migration_harness.candidate_semantic_schema import (
    FIXED_RESOURCE_LIMITS,
    FIXED_TIMEOUT_SECONDS,
    derive_strict_semantic_status,
    fixed_adapter_plan,
    semantic_raw_payload,
)
from validation.tools._project_migration_harness import candidate_semantic_runners as runners
from validation.tools._project_migration_harness.ledger import LedgerError
from validation.tools.project_migration_gate_authority_test_support import (
    ProjectMigrationGateAuthorityCase,
)


RUNNERS = {
    "oracle-replay-diff": runners.run_oracle_replay_diff_candidate,
    "negative": runners.run_negative_candidate,
    "unsafe-alias": runners.run_unsafe_alias_candidate,
    "abi-layout": runners.run_abi_layout_candidate,
}


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def observation(family: str, *, failed: bool = False) -> dict:
    values = {
        "oracle-replay-diff": {
            "case_count": 3, "mismatch_count": int(failed), "crash_count": 0,
            "c_oracle_sha256": digest("oracle"),
            "rust_replay_sha256": digest("replay"),
            "diff_sha256": digest("diff"),
        },
        "negative": {
            "case_count": 2, "unexpected_accept_count": int(failed),
            "mutation_manifest_sha256": digest("mutations"),
        },
        "unsafe-alias": {
            "unsafe_site_count": 1, "unproven_alias_count": int(failed),
            "unsafe_ledger_sha256": digest("unsafe-ledger"),
            "alias_evidence_sha256": digest("alias-evidence"),
        },
        "abi-layout": {
            "check_count": 4, "mismatch_count": int(failed),
            "c_layout_sha256": digest("c-layout"),
            "rust_layout_sha256": digest("rust-layout"),
        },
    }
    return values[family]


class CandidateSemanticRunnerTests(ProjectMigrationGateAuthorityCase):
    def setUp(self) -> None:
        super().setUp()
        self.record_candidate_host_gate("compile", "passed", "host-compile")

    def _kwargs(self) -> dict:
        return {
            "ledger": self.ledger,
            "out_root": self.out_root,
            "out_root_rel": "target/run",
            "run_id": "run",
            "unit_id": "unit",
            "candidate_artifact_id": self.candidate_id,
        }

    @staticmethod
    def _adapter(family: str, *, failed: bool = False):
        payload = canonical_json_bytes(observation(family, failed=failed))
        return runners._AdapterExecution(True, 0, False, payload, b"")

    def test_each_dedicated_runner_derives_pass_from_strict_raw_observation(self) -> None:
        plans = []

        def execute(plan, request, repository_root):
            plans.append(plan)
            request_payload = json.loads(request.decode("utf-8"))
            self.assertEqual(set(current_semantic_context(
                self.ledger, "run", "unit", self.candidate_id, "wave-provisional",
            )[0]), set(request_payload["bindings"]))
            self.assertEqual(self.harness.resolve(), repository_root)
            return self._adapter(plan["gate_family"])

        with mock.patch.object(runners, "_invoke_fixed_adapter", side_effect=execute):
            results = {family: runner(**self._kwargs()) for family, runner in RUNNERS.items()}

        self.assertTrue(all(item["gate_status"] == "passed" for item in results.values()))
        self.assertEqual(set(RUNNERS), {plan["gate_family"] for plan in plans})
        for family, result in results.items():
            raw_path = self.harness.joinpath(*Path(result["observation"]["path"]).parts)
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            self.assertNotIn("status", raw)
            self.assertNotIn("pass", raw["observation"])
            self.assertEqual("unit", raw["group_id"])
            self.assertEqual(self.candidate_sha, raw["candidate_source"]["sha256"])
            self.assertEqual(digest("toolchain"), raw["toolchain_sha256"])
            self.assertEqual(fixed_adapter_plan(family), raw["verification_plan"])
            self.assertEqual(FIXED_TIMEOUT_SECONDS, raw["verification_plan"]["timeout_seconds"])
            self.assertEqual(FIXED_RESOURCE_LIMITS, raw["verification_plan"]["resource_limits"])

    def test_public_runners_accept_no_status_command_timeout_or_observation(self) -> None:
        for runner in RUNNERS.values():
            self.assertEqual({"kwargs"}, set(inspect.signature(runner).parameters))
            for field, value in (
                ("status", "passed"), ("pass", True), ("command", ["sh"]),
                ("timeout_seconds", 1), ("observation", {}),
            ):
                with self.subTest(runner=runner.__name__, field=field):
                    with self.assertRaises(TypeError):
                        runner(**self._kwargs(), **{field: value})

    def test_unknown_adapter_fields_and_process_failures_are_blocked(self) -> None:
        bad = observation("negative")
        bad["status"] = "passed"
        executions = [
            runners._AdapterExecution(True, 0, False, canonical_json_bytes(bad), b""),
            runners._AdapterExecution(True, 7, False, b"", b"failed"),
            runners._AdapterExecution(True, None, True, b"", b"timeout"),
        ]
        for index, execution in enumerate(executions):
            with self.subTest(index=index), mock.patch.object(
                runners, "_invoke_fixed_adapter", return_value=execution,
            ):
                result = runners.run_negative_candidate(**self._kwargs())
                self.assertEqual("blocked", result["status"])
                self.assertFalse(result["candidate_gate_recorded"])
        with self.ledger.connect() as connection:
            count = connection.execute(
                "select count(*) from verifier_records where gate_family='negative'"
            ).fetchone()[0]
        self.assertEqual(0, count)

    def test_unconfigured_fixed_backend_cannot_create_a_gate(self) -> None:
        result = runners.run_negative_candidate(**self._kwargs())
        self.assertEqual("blocked", result["status"])
        self.assertFalse(result["candidate_gate_recorded"])

    def test_semantic_mismatch_records_failure_without_caller_status(self) -> None:
        with mock.patch.object(
            runners, "_invoke_fixed_adapter",
            return_value=self._adapter("negative", failed=True),
        ):
            result = runners.run_negative_candidate(**self._kwargs())
        self.assertEqual("failed", result["gate_status"])
        self.assertTrue(result["candidate_gate_recorded"])
        self.assertEqual("retryable", self.ledger.unit_states("run")[0]["resumable_status"])

    def test_path_escape_and_unknown_raw_schema_are_rejected(self) -> None:
        with mock.patch.object(
            runners, "_invoke_fixed_adapter", return_value=self._adapter("negative"),
        ), self.assertRaisesRegex(LedgerError, "output root"):
            runners.run_negative_candidate(**{
                **self._kwargs(), "out_root_rel": "../run",
            })
        context, _root = current_semantic_context(
            self.ledger, "run", "unit", self.candidate_id, "wave-provisional",
        )
        context["candidate_source"] = {
            **context["candidate_source"], "path": "../escape.rs",
        }
        plan = fixed_adapter_plan("negative")
        execution = {
            "command_sha256": plan["command_sha256"],
            "launcher_argv_sha256": plan["launcher_argv_sha256"],
            "command_started": True, "returncode": 0, "timed_out": False,
            "stdout_sha256": digest("stdout"), "stderr_sha256": digest("stderr"),
            "stdout_size_bytes": 1, "stderr_size_bytes": 0,
        }
        with self.assertRaisesRegex(LedgerError, "source path"):
            semantic_raw_payload(
                gate_family="negative", context=context,
                execution=execution, observation=observation("negative"),
            )
        context["candidate_source"]["path"] = (
            f"target/run/workers/translator/out/{self.candidate_id}.rs"
        )
        context["worker_request"] = {
            "path": "../escape.json", "sha256": digest("request"),
            "size_bytes": 1,
        }
        with self.assertRaisesRegex(LedgerError, "worker request path"):
            semantic_raw_payload(
                gate_family="negative", context=context,
                execution=execution, observation=observation("negative"),
            )

    def test_source_change_during_adapter_run_is_stale(self) -> None:
        candidate_path = self.harness.joinpath(
            "target", "run", "workers", "translator", "out", f"{self.candidate_id}.rs",
        )

        def change_source(plan, request, repository_root):
            candidate_path.write_text("changed", encoding="utf-8")
            return self._adapter(plan["gate_family"])

        with mock.patch.object(runners, "_invoke_fixed_adapter", side_effect=change_source):
            with self.assertRaises(LedgerError):
                runners.run_negative_candidate(**self._kwargs())

    def test_candidate_cohort_change_during_adapter_run_is_stale(self) -> None:
        def change_candidate(plan, request, repository_root):
            self.make_candidate("replacement-candidate")
            return self._adapter(plan["gate_family"])

        with mock.patch.object(runners, "_invoke_fixed_adapter", side_effect=change_candidate):
            with self.assertRaises(LedgerError):
                runners.run_negative_candidate(**self._kwargs())

    def test_final_reopens_strict_semantic_source_context(self) -> None:
        with mock.patch.object(
            runners, "_invoke_fixed_adapter",
            side_effect=lambda plan, request, root: self._adapter(plan["gate_family"]),
        ):
            for runner in RUNNERS.values():
                runner(**self._kwargs())
        final = verify_candidate_final(
            ledger=self.ledger, out_root=self.out_root,
            out_root_rel="target/run", run_id="run", unit_id="unit",
            candidate_artifact_id=self.candidate_id,
        )
        self.assertEqual("passed", final["gate_status"])
        candidate_path = self.harness.joinpath(
            "target", "run", "workers", "translator", "out", f"{self.candidate_id}.rs",
        )
        candidate_path.write_text("stale", encoding="utf-8")
        with self.assertRaises(LedgerError):
            verify_candidate_final(
                ledger=self.ledger, out_root=self.out_root,
                out_root_rel="target/run", run_id="run", unit_id="unit",
                candidate_artifact_id=self.candidate_id,
            )

    def test_strict_payload_rejects_unknown_top_level_field(self) -> None:
        context, _root = current_semantic_context(
            self.ledger, "run", "unit", self.candidate_id, "wave-provisional",
        )
        plan = fixed_adapter_plan("negative")
        output = canonical_json_bytes(observation("negative"))
        raw = semantic_raw_payload(
            gate_family="negative", context=context,
            execution={
                "command_sha256": plan["command_sha256"],
                "launcher_argv_sha256": plan["launcher_argv_sha256"],
                "command_started": True, "returncode": 0, "timed_out": False,
                "stdout_sha256": hashlib.sha256(output).hexdigest(),
                "stderr_sha256": hashlib.sha256(b"").hexdigest(),
                "stdout_size_bytes": len(output), "stderr_size_bytes": 0,
            },
            observation=observation("negative"),
        )
        raw["claimed_pass"] = True
        with self.assertRaisesRegex(LedgerError, "schema"):
            derive_strict_semantic_status(
                raw, run_id="run", unit_id="unit",
                candidate_artifact_id=self.candidate_id,
                candidate_sha256=self.candidate_sha,
                candidate_set_sha256=str(context["candidate_set_sha256"]),
                gate_family="negative",
            )
        raw.pop("claimed_pass")
        raw["observation"]["unexpected_accept_count"] = 1
        with self.assertRaisesRegex(LedgerError, "adapter stdout"):
            derive_strict_semantic_status(
                raw, run_id="run", unit_id="unit",
                candidate_artifact_id=self.candidate_id,
                candidate_sha256=self.candidate_sha,
                candidate_set_sha256=str(context["candidate_set_sha256"]),
                gate_family="negative",
            )


if __name__ == "__main__":
    unittest.main()
