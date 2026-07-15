from __future__ import annotations

import copy
import hashlib
import json
import unittest
from unittest import mock
import uuid

from validation.tools._project_migration_harness.make_dry_run_contract import (
    MakeDryRunContractError,
    canonical_make_dry_run_report_bytes,
    create_make_dry_run_report,
    validate_make_dry_run_report,
)
from validation.tools._project_migration_harness.make_dry_run_parser import (
    MAX_STDOUT_BYTES,
    MakeDryRunParseError,
    parse_make_dry_run_stdout,
)
from validation.tools._project_migration_harness.make_dry_run_runner import (
    canonical_make_dry_run_plan_bytes, create_make_dry_run_plan,
)
from validation.tools.test_project_migration_make_support import (
    artifact_ref, controlled_success,
)


class MakeDryRunParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.token = uuid.uuid4().hex[:12]
        self.source = f"sources/{self.token}/unit.c"
        self.object = f"output/{self.token}/unit.o"
        self.archive = f"output/{self.token}/libunit.a"
        self.program = f"output/{self.token}/program"

    def stdout(self) -> str:
        output_root = f"output/{self.token}"
        return "\n".join([
            f"clang -Iheaders -DPROFILE='neutral value' -c {self.source} -o {self.object}",
            f"llvm-ar rcs {self.archive} {self.object}",
            f"llvm-ranlib {self.archive}",
            f"clang {self.object} -L{output_root} -lunit -o {self.program}",
            f"ld.lld -shared -o {output_root}/module.so {self.object} -lunit",
            "",
        ])

    def ref(self, path: str) -> dict[str, object]:
        payload = f"{self.token}:{path}".encode("utf-8")
        return {
            "path": path,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }

    @staticmethod
    def raw_ref(path: str, payload: bytes) -> dict[str, object]:
        return {
            "path": path,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }

    def report(self) -> dict[str, object]:
        makefile = self.ref(f"inputs/{self.token}/project.mk")
        source = self.ref(self.source)
        toolchain = self.ref(f"evidence/{self.token}/toolchain.json")
        plan = create_make_dry_run_plan(
            makefile_ref=makefile,
            input_refs=[source],
            toolchain_ref=toolchain,
            targets=[f"target-{self.token}"],
        )
        stdout = self.stdout().encode("utf-8")
        outcome, sandbox, _sandbox_bytes = controlled_success(
            plan, toolchain, stdout, b"",
            sandbox_path=f"evidence/{self.token}/sandbox.json",
        )
        return create_make_dry_run_report(
            outcome=outcome,
            raw_stdout_ref=self.raw_ref(
                f"evidence/{self.token}/cas/raw-stdout/"
                f"{hashlib.sha256(stdout).hexdigest()}.bin",
                stdout,
            ),
            raw_stderr_ref=self.raw_ref(
                f"evidence/{self.token}/cas/raw-stderr/"
                f"{hashlib.sha256(b'').hexdigest()}.bin",
                b"",
            ),
            makefile_ref=makefile,
            source_refs=[source],
            input_refs=[source],
            toolchain_ref=toolchain,
            sandbox_ref=sandbox,
            execution_plan_ref=artifact_ref(
                f"evidence/{self.token}/plan.json",
                canonical_make_dry_run_plan_bytes(plan),
            ),
            targets=[f"target-{self.token}"],
        )

    def test_parses_only_direct_tool_argv(self) -> None:
        parsed = parse_make_dry_run_stdout(self.stdout())

        self.assertEqual(
            ["compile", "archive", "ranlib", "link", "link"],
            [command["kind"] for command in parsed["commands"]],
        )
        compile_command = parsed["commands"][0]
        self.assertEqual([self.source], compile_command["inputs"])
        self.assertEqual([self.object], compile_command["outputs"])
        self.assertEqual("-DPROFILE=neutral value", compile_command["argv"][2])
        self.assertEqual([self.archive], parsed["commands"][2]["outputs"])
        self.assertEqual(
            hashlib.sha256(self.stdout().encode("utf-8")).hexdigest(),
            parsed["raw_stdout"]["sha256"],
        )

    def test_preserves_absolute_tool_selection_without_executing_it(self) -> None:
        tool = "C:/toolchains/clang"
        parsed = parse_make_dry_run_stdout(
            f"{tool} -c {self.source} -o {self.object}\n"
        )

        self.assertEqual(tool, parsed["commands"][0]["tool"])
        self.assertEqual(tool, parsed["commands"][0]["argv"][0])

    def test_subdirectory_parent_paths_normalize_inside_repository(self) -> None:
        parsed = parse_make_dry_run_stdout(
            "cc -I../include -c ../src/unit.c -o obj/unit.o\n"
            "cc obj/unit.o ../../vendor/prebuilt.a -o app\n",
            working_directory="components/build",
        )

        self.assertEqual(
            ["components/src/unit.c"], parsed["commands"][0]["inputs"],
        )
        self.assertEqual(
            ["components/build/obj/unit.o"], parsed["commands"][0]["outputs"],
        )
        self.assertEqual(
            ["components/build/obj/unit.o", "vendor/prebuilt.a"],
            parsed["commands"][1]["inputs"],
        )
        with self.assertRaisesRegex(MakeDryRunParseError, "path_escape"):
            parse_make_dry_run_stdout(
                "cc -c ../../../outside.c -o obj/unit.o\n",
                working_directory="components/build",
            )

    def test_report_is_versioned_canonical_and_claims_no_semantics(self) -> None:
        report = self.report()
        encoded = canonical_make_dry_run_report_bytes(report)

        self.assertEqual(3, report["schema_version"])
        self.assertEqual("project-migration-make-dry-run-report", report["artifact_kind"])
        self.assertFalse(report["semantic_gate"])
        self.assertEqual(0, report["translation_coverage_numerator"])
        self.assertFalse(report["configure_executed"])
        self.assertEqual(self.source, report["source_refs"][0]["path"])
        self.assertEqual(
            ["make", "-B", "-n", "-j1", "--no-print-directory", "-f",
             f"inputs/{self.token}/project.mk", "--", f"target-{self.token}"],
            report["make_argv"],
        )
        self.assertEqual(encoded, canonical_make_dry_run_report_bytes(report))
        self.assertEqual(report, json.loads(encoded))
        self.assertEqual(report, validate_make_dry_run_report(report))

    def test_report_rejects_policy_tampering_and_unbound_sources(self) -> None:
        report = self.report()
        for key, replacement in (
            ("schema_version", True),
            ("semantic_gate", True),
            ("translation_coverage_numerator", 1),
            ("translation_coverage_numerator", False),
            ("configure_executed", True),
            ("explicitly_enabled", False),
            ("command_count", True),
        ):
            with self.subTest(key=key):
                changed = copy.deepcopy(report)
                changed[key] = replacement
                with self.assertRaises(MakeDryRunContractError):
                    validate_make_dry_run_report(changed)

        changed = copy.deepcopy(report)
        changed["commands"][0]["argv"][0] = "echo"
        with self.assertRaisesRegex(MakeDryRunContractError, "command_binding_invalid"):
            validate_make_dry_run_report(changed)

        changed = copy.deepcopy(report)
        changed["targets"] = tuple(changed["targets"])
        with self.assertRaisesRegex(MakeDryRunContractError, "targets_invalid"):
            validate_make_dry_run_report(changed)

        changed = copy.deepcopy(report)
        changed["source_refs"] = [self.ref(f"sources/{self.token}/other.c")]
        with self.assertRaisesRegex(MakeDryRunContractError, "source_binding_mismatch"):
            validate_make_dry_run_report(changed)

        with self.assertRaisesRegex(MakeDryRunContractError, "runner_outcome_type_invalid"):
            create_make_dry_run_report(
                outcome={"status": "ready"},
                raw_stdout_ref=report["raw_stdout_ref"],
                raw_stderr_ref=report["raw_stderr_ref"],
                makefile_ref=report["makefile_ref"],
                source_refs=report["source_refs"], input_refs=report["input_refs"],
                toolchain_ref=report["toolchain_ref"],
                sandbox_ref=report["sandbox_ref"],
                execution_plan_ref=report["execution_plan_ref"],
                targets=report["targets"],
            )

        extra = copy.deepcopy(report)
        extra["unversioned_extension"] = True
        with self.assertRaisesRegex(MakeDryRunContractError, "fields_invalid"):
            validate_make_dry_run_report(extra)

    def test_parser_never_calls_process_apis(self) -> None:
        with mock.patch("subprocess.Popen", side_effect=AssertionError("process started")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process started")):
            parsed = parse_make_dry_run_stdout(self.stdout())
            report = self.report()

        self.assertEqual(5, len(parsed["commands"]))
        self.assertEqual("ready", report["status"])

    def test_rejects_control_wrappers_ambiguity_escape_and_unknowns(self) -> None:
        compile_line = f"clang -c {self.source} -o {self.object}"
        rejected = {
            "command_chain": compile_line + " && echo done",
            "shell_control": compile_line + "; echo done",
            "pipeline": compile_line + " | tee record.txt",
            "redirect": compile_line + " > record.txt",
            "cd": "cd sources",
            "shell": f"sh -c '{compile_line}'",
            "recursive_make": "make -C nested all",
            "configure": "./configure --quiet",
            "libtool": f"libtool --mode=compile {compile_line}",
            "compile_link": f"clang {self.source} -o {self.program}",
            "mixed_compile_link": f"clang -c {self.source} {self.object} -o {self.object}",
            "absolute_source": f"clang -c /temporary/unit.c -o {self.object}",
            "relative_escape": f"clang -I../headers -c {self.source} -o {self.object}",
            "absolute_link_path": f"clang {self.object} -Wl,-rpath,/outside -o {self.program}",
            "tool_path": f"./clang -c {self.source} -o {self.object}",
            "response_file": "clang @arguments.rsp -o output/unit.o",
            "unknown": "echo completed",
        }
        for name, stdout in rejected.items():
            with self.subTest(name=name):
                with self.assertRaises(MakeDryRunParseError):
                    parse_make_dry_run_stdout(stdout + "\n")

    def test_rejects_invalid_encoding_and_output_flood(self) -> None:
        with self.assertRaisesRegex(MakeDryRunParseError, "stdout_not_utf8"):
            parse_make_dry_run_stdout(b"\xff")
        with self.assertRaisesRegex(MakeDryRunParseError, "stdout_limit_exceeded"):
            parse_make_dry_run_stdout(b"x" * (MAX_STDOUT_BYTES + 1))


if __name__ == "__main__":
    unittest.main()
