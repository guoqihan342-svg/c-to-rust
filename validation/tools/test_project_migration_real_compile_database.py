from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.c2rust_project_baseline import (
    run_c2rust_project_baseline,
)
from validation.tools._project_migration_harness.c2rust_project_baseline_compile_db import (
    normalize_compilation_database,
)
from validation.tools._project_migration_harness.c2rust_project_baseline_diagnostics import (
    has_transpiler_error_diagnostics,
)
from validation.tools._project_migration_harness.discovery import discover_project
from validation.tools.project_migration_c2rust_baseline_test_support import FakeRunner


class RealCompileDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="real-compile-db-")
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.out = self.root / "out"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "include").mkdir()
        (self.repo / "src/unit.c").write_text(
            "int main(void) { return 0; }\n", encoding="utf-8",
        )
        self.database = self.repo / "compile_commands.json"
        self._write_entries([self._baseline_entry()])
        self.tools: dict[str, Path] = {}
        for name in ("c2rust-transpile", "cargo", "rustc"):
            path = self.root / "tools" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name + "\n", encoding="utf-8")
            self.tools[name] = path

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_baseline_ignores_paired_bear_clang_frontend_job(self) -> None:
        self._write_entries([self._baseline_entry(), self._frontend_entry()])

        normalized = normalize_compilation_database(self.repo, self.database)

        self.assertEqual(1, len(normalized.entries))
        self.assertEqual(1, len(normalized.sources))
        self.assertNotIn("-cc1", normalized.entries[0]["arguments"])

    def test_baseline_rejects_unpaired_clang_frontend_job(self) -> None:
        self._write_entries([self._frontend_entry()])

        with self.assertRaisesRegex(ValueError, "internal_job_unpaired"):
            normalize_compilation_database(self.repo, self.database)

    def test_baseline_preserves_path_like_macro_values(self) -> None:
        entry = self._baseline_entry()
        entry["arguments"][1:1] = [
            '-DCONFIG_SYSROOT="/usr/aarch64-linux-gnu"',
            "-D", "CONFIG_PATH=/opt/toolchain/include",
            "-U", "DISABLED_PATH=/outside",
        ]
        self._write_entries([entry])

        normalized = normalize_compilation_database(self.repo, self.database)

        arguments = normalized.entries[0]["arguments"]
        self.assertIn('-DCONFIG_SYSROOT="/usr/aarch64-linux-gnu"', arguments)
        self.assertIn("CONFIG_PATH=/opt/toolchain/include", arguments)
        self.assertIn("DISABLED_PATH=/outside", arguments)

    def test_discovery_marks_paired_frontend_job_nonblocking(self) -> None:
        self._write_entries([
            self._discovery_entry([
                "clang", "-c", "src/unit.c", "-o", "build/unit.o",
            ]),
            self._discovery_entry([
                "/usr/lib/llvm-18/bin/clang", "-cc1", "-emit-obj",
                "-resource-dir", "/usr/lib/llvm-18/lib/clang/18",
                "-o", "/tmp/unit.o", "src/unit.c",
            ], output="/tmp/unit.o"),
        ])

        result = discover_project(self.repo, compile_database=self.database)

        self.assertEqual("ready", result["status"])
        self.assertEqual([], result["blockers"])
        self.assertEqual(1, len(result["translation_units"]))
        ignored = result["rejected_entries"][0]
        self.assertEqual("paired_clang_frontend_job_ignored", ignored["reason"])
        self.assertEqual("src/unit.c", ignored["source"])
        self.assertFalse(ignored["blocking"])

    def test_discovery_keeps_unpaired_frontend_job_blocking(self) -> None:
        self._write_entries([self._discovery_entry([
            "clang", "-cc1", "-emit-obj", "src/unit.c",
        ])])

        result = discover_project(self.repo, compile_database=self.database)

        self.assertEqual("blocked", result["status"])
        self.assertIn("compile_only_flag_missing", result["blockers"])
        self.assertTrue(result["rejected_entries"][0]["blocking"])

    def test_zero_exit_transpiler_error_blocks_before_cargo(self) -> None:
        runner = FakeRunner(
            self._generated_main(),
            transpile_stderr=b"\x1b[31merror:\x1b[0m failed translation\n",
        )

        result = self._run(runner)

        self.assertEqual("blocked", result.report["status"])
        self.assertEqual(
            ["c2rust_transpile_diagnostics_failed"], result.report["blockers"],
        )
        self.assertEqual(1, len(runner.calls))
        self.assertEqual(0, result.report["executions"][0]["returncode"])

    def test_multi_configuration_source_blocks_before_cargo(self) -> None:
        first = self._baseline_entry("-DMODE=1", "build/unit-mode-1.o")
        second = self._baseline_entry("-DMODE=2", "build/unit-mode-2.o")
        self._write_entries([first, second])
        runner = FakeRunner(self._generated_main())

        result = self._run(runner)

        self.assertEqual("blocked", result.report["status"])
        self.assertEqual(
            ["c2rust_multi_configuration_source_unsupported"],
            result.report["blockers"],
        )
        self.assertEqual(1, len(runner.calls))

    def test_transpiler_stderr_drift_is_rejected(self) -> None:
        self.out.mkdir()
        stderr = self.out / "stderr.bin"
        original = b"error: failed translation\n"
        stderr.write_bytes(original)
        binding = {
            "path": "stderr.bin",
            "sha256": hashlib.sha256(original).hexdigest(),
            "size_bytes": len(original),
        }
        stderr.write_bytes(b"warning: replaced evidence\n")

        with self.assertRaisesRegex(ValueError, "stderr_binding_invalid"):
            has_transpiler_error_diagnostics(self.out, binding)

    def _baseline_entry(
        self, define: str | None = None, output: str = "build/unit.o",
    ) -> dict:
        arguments = ["cc"]
        if define is not None:
            arguments.append(define)
        arguments.extend([
            "-I", str(self.repo / "include"), "-c",
            str(self.repo / "src/unit.c"), "-o", output,
        ])
        return {
            "directory": str(self.repo),
            "file": str(self.repo / "src/unit.c"),
            "arguments": arguments,
            "output": output,
        }

    def _frontend_entry(self) -> dict:
        return {
            "directory": str(self.repo),
            "file": str(self.repo / "src/unit.c"),
            "arguments": [
                "/usr/lib/llvm-18/bin/clang", "-cc1", "-resource-dir",
                "/usr/lib/llvm-18/lib/clang/18", "-internal-isystem",
                "/usr/include", "-o", "/tmp/unit.o", "src/unit.c",
            ],
            "output": "/tmp/unit.o",
        }

    @staticmethod
    def _discovery_entry(
        arguments: list[str], *, output: str = "build/unit.o",
    ) -> dict:
        return {
            "directory": ".", "file": "src/unit.c",
            "arguments": arguments, "output": output,
        }

    def _write_entries(self, entries: list[dict]) -> None:
        self.database.write_text(json.dumps(entries), encoding="utf-8")

    @staticmethod
    def _generated_main() -> dict[str, str]:
        return {
            "src/src/unit.rs": "pub unsafe extern \"C\" fn main() -> i32 { 0 }\n",
        }

    def _run(self, runner: FakeRunner):
        return run_c2rust_project_baseline(
            repo_root=self.repo, compile_commands=self.database,
            c2rust_transpile=self.tools["c2rust-transpile"], out_root=self.out,
            cargo=self.tools["cargo"], rustc=self.tools["rustc"],
            timeout_seconds=30, runner=runner,
        )


if __name__ == "__main__":
    unittest.main()
