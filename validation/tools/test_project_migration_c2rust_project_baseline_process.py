from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.c2rust_project_baseline_process import (
    ProcessOutcome, run_recorded_process,
)


class RecordedBaselineProcessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="c2rust-process-")
        self.root = Path(self.temporary.name)
        self.cwd = self.root / "repo"
        self.out = self.root / "out"
        self.cwd.mkdir()
        self.stdin_seen: list[bytes] = []

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_stdin_and_expected_nonzero_exit_are_hash_bound(self) -> None:
        def runner(argv, cwd, environment, timeout_seconds, stdin):
            self.stdin_seen.append(stdin)
            return ProcessOutcome(7, b"out", b"err")

        evidence, refs = run_recorded_process(
            ["tool", "fixtures/input.xml"], cwd=self.cwd,
            environment={**self._environment(), "SCENARIO_MODE": "strict"},
            timeout_seconds=10, out_root=self.out, purpose="scenario-case",
            portable_argv=["tool", "fixtures/input.xml"],
            portable_working_directory="repository/fixtures",
            stdin=b"<root/>\n", expected_returncodes=(7,),
            allowed_environment_keys=("SCENARIO_MODE",), runner=runner,
        )

        self.assertEqual("passed", evidence["status"])
        self.assertEqual([7], evidence["expected_returncodes"])
        self.assertEqual([b"<root/>\n"], self.stdin_seen)
        self.assertEqual(evidence["stdin_sha256"], refs[2]["sha256"])
        self.assertEqual(
            b"<root/>\n",
            self.out.joinpath(*Path(refs[2]["path"]).parts).read_bytes(),
        )

    def test_unexpected_exit_is_failed(self) -> None:
        def runner(argv, cwd, environment, timeout_seconds, stdin):
            return ProcessOutcome(3, b"", b"")

        evidence, _ = run_recorded_process(
            ["tool"], cwd=self.cwd, environment=self._environment(),
            timeout_seconds=10, out_root=self.out, purpose="scenario-case",
            portable_argv=["tool"], portable_working_directory="repository",
            expected_returncodes=(0, 7), runner=runner,
        )

        self.assertEqual("failed", evidence["status"])
        self.assertEqual(3, evidence["returncode"])

    def test_reserved_environment_keys_cannot_be_scenario_overrides(self) -> None:
        with self.assertRaisesRegex(ValueError, "environment_key_invalid"):
            run_recorded_process(
                ["tool"], cwd=self.cwd, environment=self._environment(),
                timeout_seconds=10, out_root=self.out, purpose="scenario-case",
                portable_argv=["tool"], portable_working_directory="repository",
                allowed_environment_keys=("PATH",),
            )

    def test_duplicate_expected_exit_is_rejected_before_runner(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected_returncodes_invalid"):
            run_recorded_process(
                ["tool"], cwd=self.cwd, environment=self._environment(),
                timeout_seconds=10, out_root=self.out, purpose="scenario-case",
                portable_argv=["tool"], portable_working_directory="repository",
                expected_returncodes=(0, 0),
            )

    def _environment(self) -> dict[str, str]:
        return {
            "CARGO_HOME": "runtime/cargo-home",
            "CARGO_NET_OFFLINE": "true",
            "CARGO_TARGET_DIR": "runtime/target",
            "CARGO_TERM_COLOR": "never",
            "HOME": "runtime/home",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": "runtime/bin",
            "RUSTC": "runtime/bin/rustc",
            "TMPDIR": "runtime/tmp",
        }


if __name__ == "__main__":
    unittest.main()
