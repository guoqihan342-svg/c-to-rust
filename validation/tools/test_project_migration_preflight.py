from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from validation.tools._ai_candidate_harness_parts.provider_runtime import (
    ProviderExecution,
    subprocess_runner_with_environment,
)
from validation.tools._project_migration_harness.opencode_environment import (
    REQUIRED_ROOTS,
    isolated_opencode_environment,
)
from validation.tools._project_migration_harness.project_preflight import (
    validate_project_worker_preflight,
)
from validation.tools._project_migration_harness.project_preflight_runner import (
    run_project_worker_preflight,
)


LOGICAL_MODEL = "DeepSeek-V4-Flash"
RESOLVED_MODEL = "opencode/deepseek-v4-flash-free"


class ProjectMigrationPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-preflight-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        agent_source = (
            Path(__file__).resolve().parents[2]
            / ".opencode/agents/c2rust-candidate.md"
        )
        agent_target = self.root / ".opencode/agents/c2rust-candidate.md"
        agent_target.parent.mkdir(parents=True)
        agent_target.write_bytes(agent_source.read_bytes())

    def test_real_preflight_path_uses_explicit_ephemeral_environment(self) -> None:
        captured: dict[str, object] = {}

        def process(
            argv: list[str], timeout: int, *, environment: dict[str, str], cwd: Path,
        ) -> ProviderExecution:
            captured.update(argv=argv, timeout=timeout, environment=environment, cwd=cwd)
            return ProviderExecution(0, f"{RESOLVED_MODEL}\n", "")

        with mock.patch(
            "validation.tools._project_migration_harness.project_preflight_runner."
            "subprocess_runner_with_environment",
            side_effect=process,
        ):
            result = run_project_worker_preflight(
                harness_root=self.root,
                out_root_rel="target/run",
                run_id="preflight-run",
                logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )
        self.assertEqual("passed", result["status"])
        self.assertEqual(["opencode", "models"], captured["argv"])
        working_directory = Path(captured["cwd"])
        self.assertNotEqual(self.root.resolve(), working_directory)
        self.assertFalse(working_directory.exists())
        environment = captured["environment"]
        self.assertIsInstance(environment, dict)
        ephemeral_paths = [Path(environment[key]) for key in (
            "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
            "XDG_STATE_HOME", "TMPDIR",
        )]
        self.assertTrue(all(not path.exists() for path in ephemeral_paths))
        validated = validate_project_worker_preflight(
            result["report"],
            harness_root=self.root,
            run_id="preflight-run",
            logical_model=LOGICAL_MODEL,
            resolved_model=RESOLVED_MODEL,
            opencode_command="opencode",
            agent="c2rust-candidate",
            variant="max",
        )
        self.assertEqual("auxiliary-local-validation", validated["proof_scope"])

    def test_credential_copy_is_bounded_ephemeral_and_does_not_mutate_global_env(self) -> None:
        source_data = self.root / "source-data"
        auth = source_data / "opencode/auth.json"
        auth.parent.mkdir(parents=True)
        auth.write_text('{"provider":"test"}\n', encoding="utf-8")
        roots = {
            name: f"target/workers/worker/{name}" for name in REQUIRED_ROOTS
        }
        before = os.environ.get("XDG_DATA_HOME")
        copied_path: Path | None = None
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(source_data)}):
            with isolated_opencode_environment(
                harness_root=self.root,
                runtime_roots=roots,
                attempt_id="attempt-1",
                fencing_token=1,
            ) as (environment, _working_directory, attestation):
                copied_path = Path(environment["XDG_DATA_HOME"]) / "opencode/auth.json"
                self.assertEqual(auth.read_bytes(), copied_path.read_bytes())
                self.assertEqual("bounded-ephemeral", attestation["credential_copy"])
                self.assertEqual(str(source_data), os.environ["XDG_DATA_HOME"])
        self.assertIsNotNone(copied_path)
        self.assertFalse(copied_path.exists())
        self.assertEqual(before, os.environ.get("XDG_DATA_HOME"))

    def test_unrelated_parent_secrets_and_credentialed_proxy_are_not_inherited(self) -> None:
        roots = {
            name: f"target/workers/secret-test/{name}" for name in REQUIRED_ROOTS
        }
        with mock.patch.dict(os.environ, {
            "UNRELATED_API_KEY": "must-not-enter-child",
            "HTTPS_PROXY": "http://user:password@proxy.invalid:8080",
        }):
            with isolated_opencode_environment(
                harness_root=self.root,
                runtime_roots=roots,
                attempt_id="attempt-secret-test",
                fencing_token=1,
            ) as (environment, _working_directory, _attestation):
                self.assertNotIn("UNRELATED_API_KEY", environment)
                self.assertNotIn("HTTPS_PROXY", environment)

    def test_agent_permission_override_is_rejected_before_probe(self) -> None:
        agent = self.root / ".opencode/agents/c2rust-candidate.md"
        text = agent.read_text(encoding="utf-8")
        agent.write_text(
            text.replace('  "*": deny', '  "*": deny\n  shell: ask'),
            encoding="utf-8",
        )
        with mock.patch(
            "validation.tools._project_migration_harness.project_preflight_runner."
            "subprocess_runner_with_environment"
        ) as probe:
            with self.assertRaisesRegex(ValueError, "permission"):
                run_project_worker_preflight(
                    harness_root=self.root,
                    out_root_rel="target/unsafe-agent",
                    run_id="unsafe-agent",
                    logical_model=LOGICAL_MODEL,
                    resolved_model=RESOLVED_MODEL,
                )
        probe.assert_not_called()

    def test_preflight_rejects_near_match_and_agent_drift(self) -> None:
        with mock.patch(
            "validation.tools._project_migration_harness.project_preflight_runner."
            "subprocess_runner_with_environment",
            return_value=ProviderExecution(
                0, f"{RESOLVED_MODEL}-lookalike\n", ""
            ),
        ):
            blocked = run_project_worker_preflight(
                harness_root=self.root,
                out_root_rel="target/near-match",
                run_id="near-match",
                logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )
        self.assertEqual("blocked", blocked["status"])
        with mock.patch(
            "validation.tools._project_migration_harness.project_preflight_runner."
            "subprocess_runner_with_environment",
            return_value=ProviderExecution(0, f"{RESOLVED_MODEL}\n", ""),
        ):
            passed = run_project_worker_preflight(
                harness_root=self.root,
                out_root_rel="target/agent-drift",
                run_id="agent-drift",
                logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )
        agent = self.root / ".opencode/agents/c2rust-candidate.md"
        agent.write_text(agent.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "authorize"):
            validate_project_worker_preflight(
                passed["report"],
                harness_root=self.root,
                run_id="agent-drift",
                logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
                opencode_command="opencode",
                agent="c2rust-candidate",
                variant="max",
            )

    def test_environment_aware_provider_runner_reuses_env_for_session_export(self) -> None:
        session_id = "session-isolated"
        response = json.dumps({
            "type": "message.part.updated",
            "sessionID": session_id,
            "part": {"type": "text", "text": "{}"},
        })
        exported = json.dumps({"info": {
            "id": session_id,
            "agent": "c2rust-candidate",
            "version": "test",
            "model": {
                "providerID": "opencode",
                "id": "deepseek-v4-flash-free",
                "variant": "max",
            },
        }})
        calls: list[dict[str, object]] = []

        def process(argv: list[str], **kwargs: object) -> object:
            calls.append({"argv": list(argv), **kwargs})
            payload = exported if "export" in argv else response
            return __import__("subprocess").CompletedProcess(
                argv, 0, stdout=payload, stderr=""
            )

        environment = os.environ.copy() | {"XDG_DATA_HOME": str(self.root / "isolated")}
        argv = [
            "opencode", "run", "--model", RESOLVED_MODEL,
            "--agent", "c2rust-candidate", "prompt",
        ]
        with mock.patch(
            "validation.tools._ai_candidate_harness_parts.provider_process.subprocess.run",
            side_effect=process,
        ):
            execution = subprocess_runner_with_environment(
                argv, 30, environment=environment, cwd=self.root
            )
        self.assertEqual(2, len(calls))
        self.assertTrue(all(call["env"] == environment for call in calls))
        self.assertTrue(all(call["cwd"] == str(self.root) for call in calls))
        self.assertEqual("opencode-session-export", execution.identity_receipt["source"])

    def test_process_start_callback_runs_only_after_successful_spawn(self) -> None:
        started: list[bool] = []
        execution = subprocess_runner_with_environment(
            [sys.executable, "-c", "print('started')"],
            30,
            environment=os.environ.copy(),
            cwd=self.root,
            on_started=lambda: started.append(True),
        )
        self.assertEqual(0, execution.returncode)
        self.assertTrue(execution.process_started)
        self.assertEqual([True], started)

        started.clear()
        with mock.patch(
            "validation.tools._ai_candidate_harness_parts.provider_process.subprocess.Popen",
            side_effect=FileNotFoundError("missing"),
        ):
            failed = subprocess_runner_with_environment(
                ["missing-opencode"],
                30,
                environment=os.environ.copy(),
                cwd=self.root,
                on_started=lambda: started.append(True),
            )
        self.assertFalse(failed.process_started)
        self.assertEqual([], started)


if __name__ == "__main__":
    unittest.main()
