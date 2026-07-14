from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools._project_migration_harness import (
    c_toolchain_reopen, c_toolchain_schema_identity, c_toolchain_schema_tools,
    host_tool_binding,
)
from validation.tools._project_migration_harness.c_toolchain_probe import (
    MAX_PROBE_STREAM_BYTES, ProbeExecution,
)
from validation.tools._project_migration_harness.c_toolchain_reopen import (
    C_TOOLCHAIN_RAW_ROLE, collect_c_toolchain_evidence,
    reopen_c_toolchain_evidence, tool_records_by_token,
    validate_c_toolchain_evidence,
)
from validation.tools._project_migration_harness.c_toolchain_test_support import (
    FakeToolchain, resign,
)
from validation.tools._project_migration_harness.host_tool_binding import (
    COMPETITION_PROFILE_PATH, competition_profile_binding,
)


class ProjectMigrationCToolchainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="c-toolchain-test-")
        self.root = Path(self.temporary.name)
        self.fake = FakeToolchain(self.root)
        self.environment = {
            "PATH": str(self.root / "private-bin"),
            "CPATH": str(self.root / "private-include"),
            "WSL_INTEROP": "/run/WSL/1_interop",
            "IGNORED_SECRET": "must-not-be-recorded",
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def collect(
        self, requests: list[dict[str, object]], **kwargs: object,
    ) -> dict:
        return collect_c_toolchain_evidence(
            requests,
            profile="development",
            environment=self.environment,
            resolver=self.fake.resolver,
            runner=self.fake.runner,
            **kwargs,
        )

    def test_gcc_binds_raw_outputs_empty_default_and_derived_linker(self) -> None:
        payload = self.collect([{
            "token": "gcc", "roles": ["compiler-driver", "linker-driver"],
        }])
        self.assertEqual(C_TOOLCHAIN_RAW_ROLE, payload["raw_fact_role"])
        self.assertEqual("ready", payload["status"])
        records = tool_records_by_token(payload)
        self.assertEqual({"gcc", "ld"}, set(records))
        self.assertEqual(["gcc"], records["ld"]["derived_from_tokens"])
        probes = {item["kind"]: item for item in records["gcc"]["probes"]}
        self.assertEqual("reported-empty/default", probes["sysroot"]["status"])
        self.assertEqual(["-print-prog-name=ld"], probes["linker-path"]["arguments"])
        self.assertEqual(
            b"x86_64-linux-gnu\n",
            base64.b64decode(probes["target"]["stdout_b64"], validate=True),
        )
        serialized = json.dumps(payload, sort_keys=True)
        self.assertNotIn(self.environment["PATH"], serialized)
        self.assertNotIn(self.environment["CPATH"], serialized)
        self.assertNotIn("must-not-be-recorded", serialized)
        validate_c_toolchain_evidence(payload)

    def test_clang_uses_no_default_config_and_no_sysroot_probe(self) -> None:
        payload = self.collect([{
            "token": "clang", "roles": ["compiler-driver", "linker-driver"],
        }])
        by_kind = {
            item["kind"]: item
            for item in tool_records_by_token(payload)["clang"]["probes"]
        }
        self.assertEqual("not-applicable", by_kind["sysroot"]["status"])
        self.assertEqual("", by_kind["sysroot"]["stdout_b64"])
        self.assertEqual("reported", by_kind["resource-dir"]["status"])
        self.assertEqual(
            ["--no-default-config", "-print-target-triple"],
            by_kind["target"]["arguments"],
        )
        self.assertFalse(any(
            "print-sysroot" in part for call in self.fake.calls for part in call
        ))

    def test_reopen_detects_binary_environment_and_probe_drift(self) -> None:
        request = [{"token": "gcc", "roles": ["compiler-driver"]}]
        stored = self.collect(request)
        self.assertEqual(stored, reopen_c_toolchain_evidence(
            stored, environment=self.environment, resolver=self.fake.resolver,
            runner=self.fake.runner,
        ))
        changed_interop = {
            **self.environment, "WSL_INTEROP": "/run/WSL/2_interop",
        }
        self.assertEqual(stored, reopen_c_toolchain_evidence(
            stored, environment=changed_interop, resolver=self.fake.resolver,
            runner=self.fake.runner,
        ))
        self.assertNotIn(
            "WSL_INTEROP",
            {item["name"] for item in stored["environment"]["variables"]},
        )
        original = self.fake.paths["gcc"].read_bytes()
        self.fake.paths["gcc"].write_bytes(b"changed-binary")
        with self.assertRaisesRegex(ValueError, "drift"):
            reopen_c_toolchain_evidence(
                stored, environment=self.environment, resolver=self.fake.resolver,
                runner=self.fake.runner,
            )
        self.fake.paths["gcc"].write_bytes(original)
        self.fake.paths["gcc"].chmod(0o755)
        changed = {**self.environment, "PATH": str(self.root / "other")}
        with self.assertRaisesRegex(ValueError, "drift"):
            reopen_c_toolchain_evidence(
                stored, environment=changed, resolver=self.fake.resolver,
                runner=self.fake.runner,
            )
        self.fake.version = "13.4.0"
        with self.assertRaisesRegex(ValueError, "drift"):
            reopen_c_toolchain_evidence(
                stored, environment=self.environment, resolver=self.fake.resolver,
                runner=self.fake.runner,
            )

    def test_timeout_and_output_flood_are_bounded_blockers(self) -> None:
        self.fake.special[("--version",)] = ProbeExecution(
            None, b"", b"", timed_out=True,
        )
        record = tool_records_by_token(self.collect([
            {"token": "gcc", "roles": ["compiler-driver"]},
        ]))["gcc"]
        self.assertIn("probe_version_timed-out", record["blockers"])
        self.fake.special[("--version",)] = ProbeExecution(
            -9, b"x" * (MAX_PROBE_STREAM_BYTES + 1), b"", flooded=True,
        )
        record = tool_records_by_token(self.collect([
            {"token": "gcc", "roles": ["compiler-driver"]},
        ]))["gcc"]
        probe = next(item for item in record["probes"] if item["kind"] == "version")
        self.assertEqual("output-flood", probe["status"])
        self.assertEqual(MAX_PROBE_STREAM_BYTES + 1, probe["stdout_size_bytes"])

    def test_profile_binding_is_cwd_independent_and_windows_blocks(self) -> None:
        expected = competition_profile_binding()
        self.assertEqual(COMPETITION_PROFILE_PATH, expected["path"])
        original = Path.cwd()
        try:
            os.chdir(self.root)
            self.assertEqual(expected, competition_profile_binding())
            payload = collect_c_toolchain_evidence(
                [{"token": "gcc", "roles": ["compiler-driver"]}],
                environment=self.environment,
                resolver=self.fake.resolver,
                runner=self.fake.runner,
                profile_binding=expected,
            )
        finally:
            os.chdir(original)
        self.assertEqual(expected, payload["profile_binding"])
        if os.name == "nt":
            self.assertIn("competition_host_os_family_mismatch", payload["blockers"])

    def test_competition_requires_exact_profile_identity(self) -> None:
        request = [{"token": "gcc", "roles": ["compiler-driver"]}]
        with self.assertRaisesRegex(ValueError, "profile_binding_required"):
            collect_c_toolchain_evidence(
                request, environment=self.environment,
                resolver=self.fake.resolver, runner=self.fake.runner,
            )
        binding = competition_profile_binding()
        binding["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "binding_drift"):
            collect_c_toolchain_evidence(
                request, environment=self.environment,
                resolver=self.fake.resolver, runner=self.fake.runner,
                profile_binding=binding,
            )

    def test_wrapper_is_hash_only_and_distributed_competition_blocks(self) -> None:
        calls = len(self.fake.calls)
        payload = collect_c_toolchain_evidence(
            [{"token": "distcc", "roles": ["compiler-wrapper"]}],
            environment=self.environment,
            resolver=self.fake.resolver,
            runner=self.fake.runner,
            profile_binding=competition_profile_binding(),
        )
        record = tool_records_by_token(payload)["distcc"]
        self.assertEqual("hash-only-wrapper", record["probe_policy"])
        self.assertTrue(all(
            item["status"] == "not-applicable" for item in record["probes"]
        ))
        self.assertIn("competition_distributed_wrapper_rejected", record["blockers"])
        self.assertEqual(calls, len(self.fake.calls))

    def test_rejects_invalid_request_roles_fields_and_caller_argv(self) -> None:
        invalid = [
            [{"token": "gcc", "roles": ["linker-driver", "compiler-driver"]}],
            [{"token": "gcc", "roles": ["archiver"]}],
            [{"token": "gcc", "roles": [{"invalid": "role"}]}],
            [{"token": "gcc", "roles": ["compiler-driver"], "argv": []}],
            [{"token": "python", "roles": ["compiler-driver"]}],
        ]
        for request in invalid:
            with self.subTest(request=request), self.assertRaises(ValueError):
                self.collect(request)
        payload = self.collect([{"token": "gcc", "roles": ["compiler-driver"]}])
        extra = copy.deepcopy(payload)
        extra["tools"][0]["argv"] = []
        with self.assertRaises(ValueError):
            validate_c_toolchain_evidence(extra)

    def test_schema_rejects_base64_hash_and_size_tampering(self) -> None:
        payload = self.collect([{"token": "gcc", "roles": ["compiler-driver"]}])
        mutations = (
            ("stdout_b64", "!"),
            ("stdout_sha256", "0" * 64),
            ("stdout_size_bytes", 1),
        )
        for field, value in mutations:
            changed = copy.deepcopy(payload)
            changed["tools"][0]["probes"][0][field] = value
            resign(changed)
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, "probe_output",
            ):
                validate_c_toolchain_evidence(changed)

    def test_invalid_utf8_is_preserved_but_never_reported(self) -> None:
        self.fake.special[("--version",)] = ProbeExecution(0, b"\xff", b"")
        payload = self.collect([{"token": "gcc", "roles": ["compiler-driver"]}])
        record = tool_records_by_token(payload)["gcc"]
        probe = next(item for item in record["probes"] if item["kind"] == "version")
        self.assertEqual("failed", probe["status"])
        self.assertEqual(b"\xff", base64.b64decode(probe["stdout_b64"], validate=True))
        self.assertIn("probe_version_failed", record["blockers"])

    def test_schema_independently_rejects_role_and_basename_family_tampering(self) -> None:
        payload = self.collect([{"token": "gcc", "roles": ["compiler-driver"]}])
        changed = copy.deepcopy(payload)
        changed["requests"][0]["roles"] = ["archiver"]
        changed["tools"][0]["roles"] = ["archiver"]
        with self.assertRaisesRegex(ValueError, "role_family"):
            validate_c_toolchain_evidence(resign(changed))
        changed = copy.deepcopy(payload)
        changed["tools"][0]["family"] = "archiver"
        with self.assertRaisesRegex(ValueError, "tool_family"):
            validate_c_toolchain_evidence(resign(changed))
        changed = copy.deepcopy(payload)
        changed["tools"][0]["resolved_path"] = str(self.fake.paths["ar"])
        with self.assertRaisesRegex(ValueError, "resolved_path"):
            validate_c_toolchain_evidence(resign(changed))

    def test_request_and_tool_count_limits_fail_closed(self) -> None:
        self.assertEqual(128, host_tool_binding.MAX_TOOL_REQUESTS)
        self.assertEqual(128, host_tool_binding.MAX_TOOL_RECORDS)
        requests = [
            {"token": name, "roles": ["compiler-driver"]}
            for name in ("clang", "gcc")
        ]
        with mock.patch.object(host_tool_binding, "MAX_TOOL_REQUESTS", 1):
            with self.assertRaisesRegex(ValueError, "limit_exceeded"):
                self.collect(requests)
        payload = self.collect([{
            "token": "gcc", "roles": ["compiler-driver", "linker-driver"],
        }])
        with mock.patch.object(c_toolchain_schema_tools, "MAX_TOOL_RECORDS", 1):
            with self.assertRaisesRegex(ValueError, "limit_exceeded"):
                validate_c_toolchain_evidence(payload)
        with mock.patch.object(c_toolchain_reopen, "MAX_TOOL_RECORDS", 1):
            limited = self.collect(payload["requests"])
        self.assertIn("tool_record_limit_exceeded", limited["tools"][0]["blockers"])
        with mock.patch.object(c_toolchain_schema_identity, "MAX_TOOL_REQUESTS", 0):
            with self.assertRaisesRegex(ValueError, "limit_exceeded"):
                validate_c_toolchain_evidence(payload)

    def test_tool_index_is_a_defensive_copy(self) -> None:
        payload = self.collect([{"token": "ar", "roles": ["archiver"]}])
        index = tool_records_by_token(payload)
        index["ar"]["roles"].append("linker")
        self.assertEqual(["archiver"], payload["tools"][0]["roles"])


if __name__ == "__main__":
    unittest.main()
