from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import validation.tools.project_migration_harness as entrypoint
from validation.tools._project_migration_harness.project_migration_cli import (
    output_binding,
    parse_args,
)


class ProjectMigrationCliAuthorityTests(unittest.TestCase):
    def test_candidate_gate_cli_has_no_caller_authority_or_pass_switch(self) -> None:
        base = [
            "record-candidate-gate",
            "--db", "ledger.sqlite3",
            "--out-root", "target/run",
            "--run-id", "run",
            "--unit-id", "unit",
            "--candidate-artifact-id", "candidate",
            "--record-id", "record",
            "--gate-family", "compile",
            "--diagnostics", "diagnostics.json",
        ]
        parsed = parse_args(base)
        self.assertFalse(hasattr(parsed, "status"))
        self.assertFalse(hasattr(parsed, "verifier_id"))
        self.assertFalse(hasattr(parsed, "kind"))
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args([*base, "--status", "passed"])

    def test_project_gate_and_completion_derive_current_candidate_set(self) -> None:
        gate = parse_args([
            "record-project-gate",
            "--db", "ledger.sqlite3",
            "--out-root", "target/run",
            "--run-id", "run",
            "--record-id", "record",
            "--gate-kind", "integration",
            "--source-evidence", "evidence.json",
        ])
        self.assertFalse(hasattr(gate, "candidate_set_sha256"))
        self.assertFalse(hasattr(gate, "status"))
        self.assertFalse(hasattr(gate, "verifier_id"))
        complete = parse_args(["complete", "--db", "ledger.sqlite3", "--run-id", "run"])
        self.assertFalse(hasattr(complete, "candidate_set_sha256"))
        for command, extra in (
            ("verify-integration", ["--project-root", "project"]),
            (
                "verify-cargo",
                ["--project-root", "project", "--runtime-root", "runtime"],
            ),
            ("verify-final", []),
        ):
            parsed = parse_args([
                command,
                "--db", "ledger.sqlite3",
                "--run-id", "run",
                "--out-root", "target/run",
                *extra,
            ])
            self.assertFalse(hasattr(parsed, "status"))
            self.assertFalse(hasattr(parsed, "verifier_id"))
            self.assertFalse(hasattr(parsed, "candidate_set_sha256"))

    def test_runtime_cli_fixes_command_and_requires_attempt_fence(self) -> None:
        preflight = parse_args([
            "preflight",
            "--out-root", "target/run",
            "--run-id", "run",
        ])
        self.assertFalse(hasattr(preflight, "opencode_command"))
        self.assertFalse(hasattr(preflight, "agent"))
        self.assertFalse(hasattr(preflight, "variant"))
        worker = parse_args([
            "run-worker",
            "--request-path", "request.json",
            "--request-sha256", "a" * 64,
            "--preflight-path", "preflight.json",
            "--preflight-sha256", "b" * 64,
            "--db", "ledger.sqlite3",
        ])
        self.assertFalse(hasattr(worker, "opencode_command"))
        ingest = parse_args([
            "ingest",
            "--db", "ledger.sqlite3",
            "--run-id", "run",
            "--worker-id", "worker",
            "--attempt-id", "attempt",
            "--fencing-token", "7",
            "--response", "response.json",
        ])
        self.assertEqual(7, ingest.fencing_token)

    def test_dispatch_binding_rejects_ledger_escape_before_open(self) -> None:
        with tempfile.TemporaryDirectory(prefix="migration-cli-binding-") as temporary:
            root = Path(temporary)
            plan_path = root / "target" / "run" / "project-migration-plan.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text("{}", encoding="utf-8")
            plan = _plan("../outside.sqlite3")

            with self.assertRaisesRegex(SystemExit, "canonical"):
                output_binding(plan, plan_path=plan_path, harness_root=root)

            self.assertFalse((root / "outside.sqlite3").exists())

    def test_dispatch_binding_matches_plan_output_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="migration-cli-binding-") as temporary:
            root = Path(temporary)
            plan_path = root / "target" / "run" / "project-migration-plan.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text("{}", encoding="utf-8")

            ledger, out_root = output_binding(
                _plan("target/run/state/project-migration.sqlite3"),
                plan_path=plan_path,
                harness_root=root,
            )

            self.assertEqual("target/run/state/project-migration.sqlite3", ledger)
            self.assertEqual("target/run", out_root.as_posix())

    def test_prelaunch_and_manual_reconcile_return_nonzero(self) -> None:
        with tempfile.TemporaryDirectory(prefix="migration-cli-exit-") as temporary:
            root = Path(temporary)
            for status in ("prelaunch-blocked", "manual-reconcile"):
                with (
                    mock.patch.object(entrypoint, "REPO_ROOT", root),
                    mock.patch.object(
                        entrypoint,
                        "run_project_worker_preflight",
                        return_value={"schema_version": 1, "status": status},
                    ),
                    redirect_stdout(io.StringIO()),
                ):
                    code = entrypoint.main([
                        "preflight", "--out-root", "target/run", "--run-id", "run",
                    ])
                self.assertEqual(1, code)


def _plan(ledger_path: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "planned",
        "run_id": "run",
        "portfolio": {"status": "planned", "run_id": "run"},
        "ledger": {
            "path": ledger_path,
            "resume_policy": "create_or_verify_immutable_inputs",
            "schema_version": 2,
            "status": "bound",
        },
    }


if __name__ == "__main__":
    unittest.main()
