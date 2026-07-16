from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.model_safe_test_contract import (
    build_model_safe_test_contract,
)
from validation.tools._project_migration_harness.project_test_input_snapshot import (
    materialize_project_test_input_snapshot,
)
from validation.tools._project_migration_harness.project_test_inventory_automake import (
    select_make_test_command,
)
from validation.tools._project_migration_harness.project_test_inventory_make import (
    inventory_from_make_observation,
)
from validation.tools._project_migration_harness.project_test_inventory_make_command import (
    parse_direct_make_test_command,
)
from validation.tools._project_migration_harness.project_test_oracle_evidence import (
    build_project_oracle_evidence,
)
from validation.tools._project_migration_harness.project_test_process_sandbox import (
    execute_isolated_project_test_process,
    public_process_result,
)
from validation.tools._project_migration_harness.project_test_stdin import (
    read_snapshot_stdin,
)
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract, canonical_sha256,
)
from validation.tools._project_migration_harness.sandbox_requirements import (
    strict_sandbox_requirements,
)
from validation.tools.project_migration_sandbox_test_support import (
    passing_probe_receipt,
)


class ProjectTestStdinTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-test-stdin-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.build = self.root / "build"
        self.build.mkdir()
        self.binary = self.build / "suite-bin"
        self.binary.write_bytes(b"native-test-binary")
        self.fixture = self.root / "fixture.bin"
        self.fixture.write_bytes(b"logic-input\x00\xff\n")

    def test_make_redirection_becomes_bounded_stdin_input(self) -> None:
        inventory = self.inventory("./suite-bin --strict < ../fixture.bin")

        self.assertEqual("ready", inventory["status"], inventory)
        test = inventory["tests"][0]
        self.assertEqual(
            [{"kind": "literal", "value": "--strict"}],
            test["arguments"],
        )
        self.assertEqual(
            {"kind": "repo-path", "path": "fixture.bin"}, test["stdin"],
        )
        snapshot = materialize_project_test_input_snapshot(
            self.root, self.root / "snapshot", inventory,
        )
        self.assertEqual(["fixture.bin"], snapshot["required_inputs"])
        self.assertEqual(
            self.fixture.read_bytes(),
            read_snapshot_stdin(
                self.root / "snapshot", test["stdin"], snapshot,
            ),
        )
        copied = self.root / "snapshot" / "fixture.bin"
        copied.write_bytes(b"X" * len(self.fixture.read_bytes()))
        with self.assertRaisesRegex(ValueError, "snapshot_drifted"):
            read_snapshot_stdin(
                self.root / "snapshot", test["stdin"], snapshot,
            )

        scope_payload = {
            "reachable_target_ids": ["link-target"],
            "terminal_target_ids": ["link-target"],
        }
        contract = build_model_safe_test_contract(
            inventory, group_id="unit-a",
            target_scope={
                **scope_payload, "scope_sha256": content_sha256(scope_payload),
            },
        )
        projected = contract["tests"][0]
        self.assertEqual("repo-path", projected["stdin_shape"])
        self.assertEqual(["fixture.bin"], projected["input_paths"])
        self.assertNotIn("logic-input", str(contract))

    def test_stdin_parser_rejects_unsafe_or_unbound_redirection(self) -> None:
        cases = {
            "./suite-bin < ../missing.bin": "project_test_stdin_path_invalid",
            "./suite-bin <../fixture.bin": "project_test_make_stdin_redirection_invalid",
            "./suite-bin << ../fixture.bin": "project_test_make_stdin_redirection_invalid",
            "./suite-bin < ../fixture.bin extra": "project_test_make_stdin_redirection_invalid",
            "./suite-bin < ../fixture.bin < ../fixture.bin": "project_test_make_stdin_redirection_invalid",
            "./suite-bin < ../fixture.bin > result": "project_test_make_shell_control_rejected",
            "./suite-bin < ../fixture.bin | cat": "project_test_make_shell_control_rejected",
            "./suite-bin < ~/fixture.bin": "project_test_make_shell_control_rejected",
        }
        for command, expected in cases.items():
            with self.subTest(command=command):
                inventory = self.inventory(command)
                self.assertEqual("blocked", inventory["status"])
                self.assertEqual(expected, inventory["blockers"][0]["code"])

    def test_stdin_workspace_marker_is_anchored_and_argument_limit_matches_runner(self) -> None:
        nested = self.build / "workspace" / "input.bin"
        nested.parent.mkdir()
        nested.write_bytes(b"nested")
        inventory = self.inventory("./suite-bin < ./workspace/input.bin")
        self.assertEqual(
            {"kind": "repo-path", "path": "build/workspace/input.bin"},
            inventory["tests"][0]["stdin"],
        )
        argument_inventory = self.inventory(
            "./suite-bin ./workspace/input.bin",
        )
        self.assertEqual(
            [{"kind": "repo-path", "path": "build/workspace/input.bin"}],
            argument_inventory["tests"][0]["arguments"],
        )

        accepted = ["./suite-bin", *[f"a{index}" for index in range(128)]]
        self.assertEqual(
            (accepted, None), parse_direct_make_test_command(" ".join(accepted)),
        )
        rejected = [*accepted, "overflow"]
        with self.assertRaisesRegex(ValueError, "command_invalid"):
            parse_direct_make_test_command(" ".join(rejected))

    def test_sandbox_forwards_and_hash_binds_standard_input(self) -> None:
        launcher = self.root / "bwrap"
        launcher.write_bytes(b"launcher")
        launcher.chmod(0o755)
        subject = self.root / "subject"
        subject.write_bytes(b"subject")
        subject.chmod(0o755)
        workspace = self.root / "workspace"
        (workspace / "work").mkdir(parents=True)
        runtime = self.root / "runtime"
        contract = SandboxContract(
            backend="bubblewrap-v1", launcher_sha256="1" * 64,
            toolchain_sha256="2" * 64,
            requirements=strict_sandbox_requirements(cpu_seconds=60),
        )
        probe = passing_probe_receipt(contract)
        standard_input = b"bounded-input\x00\xff\n"
        seen: dict[str, bytes] = {}

        def executor(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            seen["input"] = kwargs["input"]  # type: ignore[assignment]
            marker_index = argv.index("/runtime/command.started")
            (runtime / "command.started").write_text(
                f"{argv[marker_index - 2]}\n{argv[marker_index - 1]}\n",
                encoding="ascii",
            )
            return subprocess.CompletedProcess(argv, 0)

        result = execute_isolated_project_test_process(
            launcher=launcher, contract=contract, executor=executor,
            executable=subject, workspace=workspace, runtime=runtime,
            arguments=["--strict"], working_directory="work",
            environment={}, timeout_seconds=30, input_sha256="a" * 64,
            standard_input=standard_input, probe_receipt=probe,
        )

        self.assertEqual("completed", result["status"])
        self.assertEqual(standard_input, seen["input"])
        self.assertEqual(
            hashlib.sha256(standard_input).hexdigest(),
            result["invocation"]["stdin_sha256"],
        )
        public = public_process_result(result)
        self.assertEqual(len(standard_input), public["invocation"]["stdin_size_bytes"])
        self.assertNotIn(standard_input.hex(), str(public))

    def test_oracle_rejects_equal_output_from_different_stdin(self) -> None:
        inventory = self.inventory("./suite-bin < ../fixture.bin")
        test_id = inventory["tests"][0]["test_id"]
        oracle = _process_result(b"first", executable_sha256="1" * 64)
        replay = _process_result(b"second", executable_sha256="2" * 64)

        evidence = build_project_oracle_evidence(
            inventory=inventory, mapping={"mapping_sha256": "3" * 64},
            oracle_results={test_id: oracle}, replay_results={test_id: replay},
        )

        self.assertEqual(1, evidence["mismatch_count"])
        self.assertFalse(evidence["cases"][0]["matched"])

    def inventory(self, command: str) -> dict:
        selected = select_make_test_command(self.root)
        stdout = command + "\n"
        raw = stdout.encode("utf-8")
        observation = {
            "schema_version": 1,
            "artifact_kind": "make-dry-run-v1-observation",
            "command": selected["command"],
            "target_binding": selected["target_binding"],
            "build_directory": "build",
            "tool": {"basename": "make", "sha256": "a" * 64, "size_bytes": 1},
            "sandbox_launcher": {
                "basename": "bwrap", "sha256": "b" * 64, "size_bytes": 1,
            },
            "timeout_seconds": 30, "returncode": 0, "stdout": stdout,
            "stdout_sha256": hashlib.sha256(raw).hexdigest(),
            "stdout_size_bytes": len(raw),
            "stderr_sha256": hashlib.sha256(b"").hexdigest(),
            "stderr_size_bytes": 0, "semantic_gate": False,
        }
        observation["observation_sha256"] = content_sha256(observation)
        return inventory_from_make_observation(
            self.root, self.build_ir(), observation,
            source_observation={
                "path": "plan/make-observation.json", "sha256": "d" * 64,
                "size_bytes": 1,
            },
        )

    def build_ir(self) -> dict:
        data = self.binary.read_bytes()
        return {"targets": [{
            "target_id": "link-target", "kind": "link",
            "outputs": [{
                "path": "build/suite-bin", "kind": "file",
                "materialized": True,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }],
        }]}


def _process_result(stdin: bytes, *, executable_sha256: str) -> dict:
    invocation = {
        "schema_version": 1, "purpose": "project-test-process",
        "executable_sha256": executable_sha256, "input_sha256": "4" * 64,
        "arguments": [], "working_directory": "build", "environment": {},
        "stdin_sha256": hashlib.sha256(stdin).hexdigest(),
        "stdin_size_bytes": len(stdin), "timeout_seconds": 30,
        "sandbox_contract_sha256": "5" * 64,
        "sandbox_probe_receipt_sha256": "6" * 64,
    }
    output = b"same-output\n"
    return {
        "schema_version": 1, "artifact_kind": "project-test-process-result",
        "status": "completed", "reason_code": None,
        "invocation": invocation, "invocation_sha256": canonical_sha256(invocation),
        "exit_code": 0, "signal": None, "timed_out": False,
        "oversized": False, "command_started": True,
        "stdout_sha256": hashlib.sha256(output).hexdigest(),
        "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        "stdout_size_bytes": len(output), "stderr_size_bytes": 0,
        "_stdout": output, "_stderr": b"",
    }


if __name__ == "__main__":
    unittest.main()
