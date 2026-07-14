from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from validation.tools._project_migration_harness.c_toolchain_reopen import (
    collect_c_toolchain_evidence, reopen_c_toolchain_evidence,
    tool_records_by_token,
)
from validation.tools._project_migration_harness.host_tool_binding import (
    competition_profile_binding,
)
from validation.tools._project_migration_harness.orchestrator import plan_project


LIVE = os.environ.get("C2R_RUN_LIVE_TOOLCHAIN_TESTS") == "1"


@unittest.skipUnless(LIVE and os.name == "posix", "explicit Linux live gate")
class ProjectMigrationLiveCToolchainTests(unittest.TestCase):
    def test_competition_gcc_binutils_and_reopen(self) -> None:
        missing = [name for name in ("gcc", "ar", "ranlib", "ld") if not shutil.which(name)]
        self.assertEqual([], missing, f"missing competition tools: {missing}")
        evidence = collect_c_toolchain_evidence(
            [
                {"token": "ar", "roles": ["archiver"]},
                {
                    "token": "gcc",
                    "roles": ["compiler-driver", "linker-driver"],
                },
                {"token": "ranlib", "roles": ["ranlib"]},
            ],
            profile="competition",
            profile_binding=competition_profile_binding(),
        )
        self.assertEqual("ready", evidence["status"], evidence["blockers"])
        self.assertEqual("linux", evidence["host"]["system"])
        records = tool_records_by_token(evidence)
        self.assertTrue({"gcc", "ar", "ranlib"}.issubset(records))
        linker = next(
            item for item in records.values()
            if item["roles"] == ["linker"] and "gcc" in item["derived_from_tokens"]
        )
        self.assertTrue(linker["resolved_path"].startswith("/"))
        probes = {item["kind"]: item for item in records["gcc"]["probes"]}
        self.assertEqual("reported", probes["version"]["status"])
        self.assertIn("13.3.0", probes["version"]["value"])
        self.assertEqual("reported", probes["target"]["status"])
        self.assertEqual("reported-empty/default", probes["sysroot"]["status"])
        self.assertEqual(evidence, reopen_c_toolchain_evidence(evidence))

    def test_competition_clang_resource_and_linker(self) -> None:
        self.assertIsNotNone(shutil.which("clang"), "clang live lane unavailable")
        evidence = collect_c_toolchain_evidence(
            [{
                "token": "clang",
                "roles": ["compiler-driver", "linker-driver"],
            }],
            profile="competition",
            profile_binding=competition_profile_binding(),
        )
        self.assertEqual("ready", evidence["status"], evidence["blockers"])
        probes = {
            item["kind"]: item
            for item in tool_records_by_token(evidence)["clang"]["probes"]
        }
        self.assertEqual("reported", probes["target"]["status"])
        self.assertEqual("reported", probes["resource-dir"]["status"])
        self.assertEqual("reported", probes["linker-path"]["status"])
        self.assertEqual("not-applicable", probes["sysroot"]["status"])

    def test_whole_project_plan_binds_live_competition_toolchains(self) -> None:
        fixture = (
            Path(__file__).resolve().parents[1]
            / "fixtures"
            / "project_migration_build_ir_equivalence"
        )
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            harness = base / "harness"
            shutil.copytree(fixture, source)
            harness.mkdir()
            compiler_path = shutil.which("clang")
            self.assertIsNotNone(compiler_path, "clang live lane unavailable")
            compiler = str(Path(compiler_path).resolve(strict=True))
            database_path = source / "build/compile_commands.json"
            database = json.loads(database_path.read_text(encoding="utf-8"))
            database[0]["arguments"][0] = compiler
            database_path.write_text(
                json.dumps(database, indent=2) + "\n", encoding="utf-8",
            )
            (source / "build/CMakeFiles/program.dir/link.txt").write_text(
                f"{compiler} unit.o -o program\n", encoding="utf-8",
            )
            plan = plan_project(
                source,
                harness_root=harness,
                out_root="target/run",
                compile_database=database_path,
                require_build_closure=True,
                profile="competition",
                max_units=8,
                max_concurrency=2,
            )

            self.assertNotEqual("blocked", plan["status"], plan.get("blockers"))
            self.assertEqual("competition", plan["profile"])
            self.assertTrue(plan["execution"]["build_ir_ready"])
            self.assertTrue(plan["execution"]["build_closure_ready"])
            output = harness / "target/run"
            evidence = _read_artifact(output, plan, "c_toolchain_evidence")
            build_ir = _read_artifact(output, plan, "build_ir")
            verification = _read_artifact(output, plan, "build_ir_verification")
            self.assertEqual("ready", evidence["status"], evidence["blockers"])
            self.assertEqual("competition", evidence["profile"])
            self.assertIn(compiler, {
                item["token"] for item in evidence["requests"]
            })
            self.assertEqual("verified", verification["status"])
            self.assertEqual("competition", verification["toolchain_profile"])
            self.assertTrue(build_ir["claim_boundary"]["host_toolchain_bound"])
            self.assertEqual(
                "competition", build_ir["claim_boundary"]["toolchain_profile"],
            )
            toolchain_ids = {item["toolchain_id"] for item in build_ir["toolchains"]}
            self.assertTrue(toolchain_ids)
            self.assertIn(compiler, {
                item["driver"] for item in build_ir["toolchains"]
            })
            self.assertTrue(all(
                item["toolchain_id"] in toolchain_ids
                for item in build_ir["translation_units"]
            ))


def _read_artifact(
    output: Path, plan: dict[str, object], name: str,
) -> dict[str, object]:
    artifacts = plan["artifacts"]
    assert isinstance(artifacts, dict)
    reference = artifacts[name]
    assert isinstance(reference, dict)
    path = reference["path"]
    assert isinstance(path, str)
    value = json.loads((output / path).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


if __name__ == "__main__":
    unittest.main()
