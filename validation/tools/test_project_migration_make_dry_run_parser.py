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

    def report(self) -> dict[str, object]:
        return create_make_dry_run_report(
            stdout=self.stdout(),
            makefile_ref=self.ref(f"inputs/{self.token}/project.mk"),
            source_refs=[self.ref(self.source)],
            toolchain_ref=self.ref(f"evidence/{self.token}/toolchain.json"),
            sandbox_ref=self.ref(f"evidence/{self.token}/sandbox.json"),
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

    def test_report_is_versioned_canonical_and_claims_no_semantics(self) -> None:
        report = self.report()
        encoded = canonical_make_dry_run_report_bytes(report)

        self.assertEqual(1, report["schema_version"])
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

        with self.assertRaisesRegex(
            MakeDryRunContractError, "source_binding_mismatch"
        ):
            create_make_dry_run_report(
                stdout=self.stdout(),
                makefile_ref=self.ref(f"inputs/{self.token}/project.mk"),
                source_refs=[self.ref(f"sources/{self.token}/other.c")],
                toolchain_ref=self.ref(f"evidence/{self.token}/toolchain.json"),
                sandbox_ref=self.ref(f"evidence/{self.token}/sandbox.json"),
                targets=["all"],
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
