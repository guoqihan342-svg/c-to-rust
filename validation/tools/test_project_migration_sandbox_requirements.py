from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import unittest

from validation.tools._project_migration_harness.sandbox_requirements import (
    ENVIRONMENT_ALLOWLIST,
    REQUIRED_CAPABILITIES,
    SandboxRequirements,
    SandboxVerificationPlan,
    cargo_verification_plan,
    requirements_from_payload,
    strict_sandbox_requirements,
)


INPUT_SHA256 = "1" * 64
COMMAND = ("cargo", "check", "--all-targets", "--offline", "--locked")


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ProjectMigrationSandboxRequirementsTests(unittest.TestCase):
    def test_requirements_are_fixed_sorted_frozen_and_deterministic(self) -> None:
        first = strict_sandbox_requirements()
        second = strict_sandbox_requirements()
        expected_capabilities = {
            "network-isolation", "project-read-only", "runtime-output-isolated",
            "home-isolated-empty", "temporary-isolated", "user-isolation",
            "process-isolation", "privileges-dropped", "environment-allowlist",
            "wall-timeout", "cpu-limit", "memory-limit", "file-size-limit",
            "process-count-limit", "open-files-limit", "toolchain-read-only",
            "exit-cleanup",
        }
        self.assertEqual(tuple(sorted(expected_capabilities)), REQUIRED_CAPABILITIES)
        self.assertEqual(REQUIRED_CAPABILITIES, first.capabilities)
        self.assertEqual(tuple(sorted(ENVIRONMENT_ALLOWLIST)), first.environment_allowlist)
        self.assertEqual(first, second)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(canonical_sha256(first.payload()), first.sha256)
        self.assertNotIn("backend", first.payload())
        self.assertIn("__slots__", SandboxRequirements.__dict__)
        with self.assertRaises(FrozenInstanceError):
            first.cpu_seconds = 1  # type: ignore[misc]

    def test_capabilities_and_environment_cannot_drift(self) -> None:
        requirements = strict_sandbox_requirements()
        self.assertEqual(requirements, requirements_from_payload(requirements.payload()))
        with self.assertRaisesRegex(ValueError, "capabilities"):
            replace(requirements, capabilities=requirements.capabilities[:-1])
        with self.assertRaisesRegex(ValueError, "capabilities"):
            replace(requirements, capabilities=(*requirements.capabilities, "unknown"))
        with self.assertRaisesRegex(ValueError, "environment allowlist"):
            replace(
                requirements,
                environment_allowlist=requirements.environment_allowlist[:-1],
            )
        with self.assertRaisesRegex(ValueError, "environment allowlist"):
            SandboxRequirements(environment_allowlist=list(ENVIRONMENT_ALLOWLIST))  # type: ignore[arg-type]
        tampered = requirements.payload()
        tampered["capabilities"] = list(REQUIRED_CAPABILITIES[:-1])
        with self.assertRaisesRegex(ValueError, "capabilities"):
            requirements_from_payload(tampered)

    def test_resource_defaults_types_and_policy_bounds(self) -> None:
        requirements = strict_sandbox_requirements()
        self.assertEqual(300, requirements.cpu_seconds)
        self.assertEqual(4 * 1024 * 1024 * 1024, requirements.address_space_bytes)
        self.assertEqual(512 * 1024 * 1024, requirements.file_size_bytes)
        self.assertEqual(128, requirements.process_count)
        self.assertEqual(256, requirements.open_files)
        for changes in (
            {"cpu_seconds": 3_601},
            {"process_count": 513},
            {"open_files": 4_097},
            {"file_size_bytes": 0},
            {"file_size_bytes": 8 * 1024 * 1024 * 1024 + 1},
            {"address_space_bytes": 64 * 1024 * 1024 * 1024 + 1},
            {"address_space_bytes": True},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(requirements, **changes)

    def test_plan_is_deterministic_and_hash_binds_its_payload(self) -> None:
        requirements = strict_sandbox_requirements()
        first = cargo_verification_plan(
            "cargo-check", COMMAND, INPUT_SHA256, requirements=requirements,
        )
        second = cargo_verification_plan(
            "cargo-check", COMMAND, INPUT_SHA256, requirements=requirements,
        )
        self.assertEqual(COMMAND, first.command)
        self.assertEqual(list(COMMAND), first.payload()["command"])
        self.assertEqual(requirements.sha256, first.requirements_sha256)
        self.assertEqual(first, second)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(canonical_sha256(first.payload()), first.sha256)
        self.assertIn("__slots__", SandboxVerificationPlan.__dict__)

    def test_input_command_and_timeout_drift_change_plan_hash(self) -> None:
        baseline = cargo_verification_plan("cargo-check", COMMAND, INPUT_SHA256)
        changed = (
            cargo_verification_plan("cargo-check", COMMAND, "2" * 64),
            cargo_verification_plan(
                "cargo-check", (*COMMAND, "--workspace"), INPUT_SHA256,
            ),
            cargo_verification_plan(
                "cargo-check", COMMAND, INPUT_SHA256, timeout_seconds=301,
            ),
        )
        self.assertEqual(3, len({plan.sha256 for plan in changed}))
        for plan in changed:
            self.assertNotEqual(baseline.sha256, plan.sha256)

    def test_invalid_commands_fail_closed(self) -> None:
        bad_commands = (
            (),
            ("cargo", ""),
            ("cargo", "check;echo"),
            ("cargo", "check\x00--offline"),
            ("cargo", "check\t--offline"),
            ("sh", "-c", "cargo check"),
        )
        requirements = strict_sandbox_requirements()
        for command in bad_commands:
            with self.subTest(command=command), self.assertRaises(ValueError):
                SandboxVerificationPlan(
                    purpose="cargo-check",
                    command=command,
                    input_sha256=INPUT_SHA256,
                    timeout_seconds=300,
                    requirements_sha256=requirements.sha256,
                    requirements=requirements,
                )
        with self.assertRaises(ValueError):
            cargo_verification_plan("cargo-check", ("rustc", "--version"), INPUT_SHA256)
        with self.assertRaises(ValueError):
            cargo_verification_plan("cargo-check", list(COMMAND), INPUT_SHA256)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "size bound"):
            cargo_verification_plan(
                "cargo-check", ("cargo", "x" * 4_097), INPUT_SHA256,
            )
        with self.assertRaises(ValueError):
            cargo_verification_plan(
                "cargo-check", ("cargo", *("x" for _ in range(64))), INPUT_SHA256,
            )

    def test_invalid_purpose_hash_and_timeout_fail_closed(self) -> None:
        requirements = strict_sandbox_requirements()

        def construct(**changes: object) -> SandboxVerificationPlan:
            values = {
                "purpose": "cargo-check",
                "command": COMMAND,
                "input_sha256": INPUT_SHA256,
                "timeout_seconds": 300,
                "requirements_sha256": requirements.sha256,
                "requirements": requirements,
            }
            values.update(changes)
            return SandboxVerificationPlan(**values)  # type: ignore[arg-type]

        for purpose in ("", "../cargo", "Cargo-Check", "cargo check"):
            with self.subTest(purpose=purpose), self.assertRaises(ValueError):
                construct(purpose=purpose)
        for digest in ("1" * 63, "A" * 64, 7):
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                construct(input_sha256=digest)
        for timeout in (29, 3_601, True):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                construct(timeout_seconds=timeout)
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            construct(requirements_sha256="0" * 64)


if __name__ == "__main__":
    unittest.main()
