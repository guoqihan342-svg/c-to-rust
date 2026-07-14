from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from validation.tools._ai_candidate_harness_parts import provider
from validation.tools._ai_candidate_harness_parts import provider_runtime


class AiCandidateHarnessRuntimeLogTests(unittest.TestCase):
    def test_subprocess_runner_reads_only_sanitized_appended_provider_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-provider-log-") as tmp:
            log_path = Path(tmp) / "opencode.log"
            log_path.write_text("existing log\n", encoding="utf-8")
            secret_marker = "must-not-enter-provider-execution"

            def fake_run(argv: list[str], **kwargs: object) -> object:
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(
                        "level=ERROR providerID=zai modelID=glm-5.1 agent=c2rust-migrator "
                        "error='Insufficient balance or no resource package' "
                        f"api_key={secret_marker}\n"
                    )
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"], output=b"", stderr=b"")

            argv = [
                "opencode",
                "run",
                "--model",
                "zai/glm-5.1",
                "--agent",
                "c2rust-migrator",
                "prompt",
            ]
            with mock.patch.dict(os.environ, {provider.OPENCODE_LOG_PATH_ENV: str(log_path)}):
                with mock.patch.object(provider.subprocess, "run", side_effect=fake_run):
                    execution = provider.subprocess_runner(argv, 30)

            self.assertTrue(execution.timed_out)
            self.assertEqual(provider.PROVIDER_BALANCE_SENTINEL, execution.stderr)
            self.assertNotIn(secret_marker, execution.stderr)
            self.assertEqual(
                "provider_insufficient_balance",
                provider.classify_provider_failure(execution)["kind"],
            )

    def test_subprocess_runner_reads_provider_diagnostic_from_new_log(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-provider-new-log-") as tmp:
            log_path = Path(tmp) / "opencode.log"
            secret_marker = "must-not-enter-first-log-execution"

            def fake_run(argv: list[str], **kwargs: object) -> object:
                log_path.write_text(
                    "level=ERROR providerID=zai modelID=glm-5.1 agent=c2rust-migrator "
                    "error='Insufficient balance or no resource package' "
                    f"api_key={secret_marker}\n",
                    encoding="utf-8",
                )
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"], output=b"", stderr=b"")

            argv = [
                "opencode",
                "run",
                "--model",
                "zai/glm-5.1",
                "--agent",
                "c2rust-migrator",
                "prompt",
            ]
            with mock.patch.dict(os.environ, {provider.OPENCODE_LOG_PATH_ENV: str(log_path)}):
                with mock.patch.object(provider.subprocess, "run", side_effect=fake_run):
                    execution = provider.subprocess_runner(argv, 30)

            self.assertTrue(execution.timed_out)
            self.assertEqual(provider.PROVIDER_BALANCE_SENTINEL, execution.stderr)
            self.assertNotIn(secret_marker, execution.stderr)
            self.assertEqual(
                "provider_insufficient_balance",
                provider.classify_provider_failure(execution)["kind"],
            )

    def test_subprocess_runner_recovers_provider_diagnostic_after_nonzero_exit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-provider-exit-log-") as tmp:
            log_path = Path(tmp) / "opencode.log"
            log_path.write_text("existing log\n", encoding="utf-8")
            secret_marker = "must-not-enter-nonzero-execution"

            def fake_run(argv: list[str], **_kwargs: object) -> object:
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(
                        "level=ERROR providerID=zai modelID=glm-5.1 agent=c2rust-migrator "
                        "error='Insufficient balance or no resource package' "
                        f"api_key={secret_marker}\n"
                    )
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr="wrapper failed")

            argv = [
                "opencode",
                "run",
                "--model",
                "zai/glm-5.1",
                "--agent",
                "c2rust-migrator",
                "prompt",
            ]
            with mock.patch.dict(os.environ, {provider.OPENCODE_LOG_PATH_ENV: str(log_path)}):
                with mock.patch.object(provider.subprocess, "run", side_effect=fake_run):
                    execution = provider.subprocess_runner(argv, 30)

            self.assertFalse(execution.timed_out)
            self.assertEqual(
                f"wrapper failed\n{provider.PROVIDER_BALANCE_SENTINEL}",
                execution.stderr,
            )
            self.assertNotIn(secret_marker, execution.stderr)
            self.assertEqual(
                "provider_insufficient_balance",
                provider.classify_provider_failure(execution)["kind"],
            )

    def test_subprocess_runner_does_not_apply_log_diagnostic_after_success(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-provider-success-log-") as tmp:
            log_path = Path(tmp) / "opencode.log"
            log_path.write_text("existing log\n", encoding="utf-8")

            def fake_run(argv: list[str], **_kwargs: object) -> object:
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(
                        "level=ERROR providerID=zai modelID=glm-5.1 agent=c2rust-migrator "
                        "error='Insufficient balance or no resource package'\n"
                    )
                return subprocess.CompletedProcess(argv, 0, stdout="candidate", stderr="")

            argv = [
                "opencode",
                "run",
                "--model",
                "zai/glm-5.1",
                "--agent",
                "c2rust-migrator",
                "prompt",
            ]
            with mock.patch.dict(os.environ, {provider.OPENCODE_LOG_PATH_ENV: str(log_path)}):
                with mock.patch.object(provider.subprocess, "run", side_effect=fake_run):
                    execution = provider.subprocess_runner(argv, 30)

            self.assertEqual(0, execution.returncode)
            self.assertEqual("", execution.stderr)
            self.assertIsNone(provider.classify_provider_failure(execution))

    def test_subprocess_runner_exports_minimal_session_identity_receipt(self) -> None:
        session_id = "ses_test_identity"
        stdout = json.dumps(
            {
                "type": "message.part.updated",
                "sessionID": session_id,
                "part": {"type": "text", "text": "candidate"},
            }
        )
        export_payload = {
            "info": {
                "id": session_id,
                "agent": "c2rust-candidate",
                "version": "1.17.18",
                "model": {
                    "providerID": "opencode",
                    "id": "deepseek-v4-flash-free",
                    "variant": "max",
                },
            },
            "messages": [{"sensitive": "must-not-enter-receipt"}],
        }
        calls: list[list[str]] = []

        def fake_run(argv: list[str], **_kwargs: object) -> object:
            calls.append(list(argv))
            if "export" in argv:
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout=json.dumps(export_payload),
                    stderr="",
                )
            return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

        argv = [
            "opencode",
            "run",
            "--model",
            "opencode/deepseek-v4-flash-free",
            "--agent",
            "c2rust-candidate",
            "prompt",
        ]
        with mock.patch.object(provider_runtime.subprocess, "run", side_effect=fake_run):
            execution = provider_runtime.subprocess_runner(argv, 30)

        self.assertEqual(
            ["opencode", "export", session_id],
            calls[1],
        )
        self.assertEqual("opencode-session-export", execution.identity_receipt["source"])
        self.assertEqual(session_id, execution.identity_receipt["session_id"])
        self.assertEqual("opencode", execution.identity_receipt["provider_id"])
        self.assertEqual("deepseek-v4-flash-free", execution.identity_receipt["model_id"])
        self.assertEqual("c2rust-candidate", execution.identity_receipt["agent"])
        self.assertEqual("max", execution.identity_receipt["variant"])
        self.assertEqual("1.17.18", execution.identity_receipt["opencode_version"])
        self.assertRegex(
            execution.identity_receipt["session_export_sha256"],
            r"^[0-9a-f]{64}$",
        )
        self.assertNotIn("messages", execution.identity_receipt)
        self.assertNotIn("sensitive", json.dumps(execution.identity_receipt))

    def test_subprocess_runner_sanitizes_provider_launch_failure(self) -> None:
        argv = [
            "opencode",
            "run",
            "--model",
            "zai/glm-5.1",
            "--agent",
            "c2rust-migrator",
            "prompt",
        ]
        sensitive_detail = "C:/private/provider/opencode.exe"
        with mock.patch.object(
            provider.subprocess,
            "run",
            side_effect=FileNotFoundError(sensitive_detail),
        ):
            execution = provider.subprocess_runner(argv, 30)

        self.assertEqual(127, execution.returncode)
        self.assertEqual(provider.PROVIDER_INVOCATION_SENTINEL, execution.stderr)
        self.assertNotIn(sensitive_detail, execution.stderr)
        self.assertEqual(
            "provider_invocation_failed",
            provider.classify_provider_failure(execution)["kind"],
        )


if __name__ == "__main__":
    unittest.main()
