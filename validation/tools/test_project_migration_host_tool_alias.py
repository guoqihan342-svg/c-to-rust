from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from validation.tools._project_migration_harness.c_toolchain_reopen import (
    collect_c_toolchain_evidence,
    reopen_c_toolchain_evidence,
    tool_records_by_token,
    validate_c_toolchain_evidence,
)


class ProjectMigrationHostToolAliasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="host-tool-alias-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.suffix = ".exe" if os.name == "nt" else ""

    def executable(self, name: str) -> Path:
        path = self.root / f"{name}{self.suffix}"
        path.write_bytes(name.encode("ascii"))
        path.chmod(0o755)
        return path.resolve()

    @staticmethod
    def runner(
        argv: list[str], **_kwargs: object,
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(argv, 0, b"LLVM version 18.1.3\n", b"")

    def collect(self, resolved: Path) -> dict:
        def resolver(_token: str, **_kwargs: object) -> str:
            return str(resolved)

        return collect_c_toolchain_evidence(
            [{"token": "llvm-ranlib", "roles": ["ranlib"]}],
            profile="development",
            environment={"PATH": str(self.root)},
            resolver=resolver,
            runner=self.runner,
        )

    def test_accepts_llvm_ranlib_multicall_alias_and_reopens_evidence(self) -> None:
        resolved = self.executable("llvm-ar")
        evidence = self.collect(resolved)

        self.assertEqual("ready", evidence["status"])
        record = tool_records_by_token(evidence)["llvm-ranlib"]
        self.assertEqual("ranlib", record["family"])
        self.assertEqual(str(resolved), record["resolved_path"])
        validate_c_toolchain_evidence(evidence)

        def resolver(_token: str, **_kwargs: object) -> str:
            return str(resolved)

        self.assertEqual(
            evidence,
            reopen_c_toolchain_evidence(
                evidence,
                environment={"PATH": str(self.root)},
                resolver=resolver,
                runner=self.runner,
            ),
        )

    def test_rejects_unrelated_archiver_as_ranlib_target(self) -> None:
        evidence = self.collect(self.executable("gcc-ar"))

        self.assertEqual("blocked", evidence["status"])
        record = tool_records_by_token(evidence)["llvm-ranlib"]
        self.assertEqual(["resolved_tool_family_mismatch"], record["blockers"])


if __name__ == "__main__":
    unittest.main()
