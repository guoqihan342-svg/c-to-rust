import json
import hashlib
import importlib.util
import jsonschema
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"
VALIDATOR = REPO_ROOT / "validation" / "tools" / "validate_auto_translation_evidence.py"


def load_auto_migrate_module():
    spec = importlib.util.spec_from_file_location("auto_migrate_under_test", AUTO_MIGRATE)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load auto_migrate module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AutoMigrateTests(unittest.TestCase):
    def _env_with_clang_path(self) -> dict[str, str]:
        environment = dict(os.environ)
        if environment.get("CLANG_PATH"):
            return environment
        default_clang = Path("C:/Program Files/LLVM/bin/clang.exe")
        if not default_clang.exists():
            self.skipTest("CLANG_PATH is required for real clang-lowering-report generation tests")
        environment["CLANG_PATH"] = str(default_clang)
        return environment

    def test_write_text_preserves_lf_bytes_for_hash_stable_evidence(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            output_path = Path(tmp) / "evidence.json"

            module.write_text(output_path, "{\n  \"status\": \"recorded\"\n}\n")

            self.assertEqual(output_path.read_bytes(), b'{\n  "status": "recorded"\n}\n')

    def test_real_fdb_crc32_fixture_includes_non_empty_check_vector(self) -> None:
        fixture_path = REPO_ROOT / "validation" / "l2_slices" / "fixtures" / "real-fdb-calc-crc32.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        cases = {case["id"]: case for case in fixture["cases"]}

        self.assertEqual(fixture["case_count"], len(fixture["cases"]))
        self.assertEqual(fixture["compared_fields"], ["return_code"])
        self.assertIn("ascii-123456789-crc-zero", cases)
        self.assertEqual(
            cases["ascii-123456789-crc-zero"],
            {
                "buf": [49, 50, 51, 52, 53, 54, 55, 56, 57],
                "coverage_kind": "standard_crc32_check_vector",
                "crc": 0,
                "id": "ascii-123456789-crc-zero",
                "return_code": 3421780262,
                "size": 9,
                "status": "draft_expected_from_standard_crc32_check_vector",
            },
        )

    def test_oracle_fixture_binding_resolves_expected_outputs_from_fixture_case_refs(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            fixture_path = Path(tmp) / "fixture.json"
            fixture_path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {"id": "case-zero", "value": 7, "input_only": "zero"},
                            {"id": "case-one", "value": 42, "input_only": "one"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            fixture_ref = fixture_path.as_posix()
            spec = {
                "fixture_contract": {
                    "path": fixture_ref,
                    "cases": [
                        {
                            "id": "case-one",
                            "input_ref": "cases[1]",
                            "expected_ref": fixture_ref,
                        }
                    ],
                    "observable_outputs": ["value"],
                    "behavior_fields": ["value"],
                }
            }

            binding = module.oracle_fixture_binding(spec)

            self.assertEqual(binding["case_count"], 1)
            self.assertEqual(binding["case_bindings"][0]["expected_outputs"], {"value": 42})
            self.assertEqual(binding["case_bindings"][0]["missing_observable_outputs"], [])
            self.assertNotIn("input_only", binding["case_bindings"][0]["expected_outputs"])
            self.assertEqual(binding["expected_output_status"], "declared_not_executed")

    def test_oracle_harness_draft_calls_bound_empty_buffer_fixture(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            fixture_path = tmp_path / "real-fdb-calc-crc32.json"
            fixture_path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "empty-crc-zero",
                                "crc": 0,
                                "buf": [],
                                "size": 0,
                                "return_code": 0,
                            },
                            {
                                "id": "ascii-123456789-crc-zero",
                                "crc": 0,
                                "buf": [49, 50, 51, 52, 53, 54, 55, 56, 57],
                                "size": 9,
                                "return_code": 3421780262,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            fixture_ref = fixture_path.as_posix()
            spec = {
                "target_id": "flashdb",
                "slice_id": "real-fdb-calc-crc32",
                "source_commit": "1234567",
                "function_name": "fdb_calc_crc32",
                "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
                "fixture_hash": "real-fdb-calc-crc32-fixture",
                "build_profile": {
                    "include_paths": [],
                    "defines": [],
                    "compiler_command_source": "unit-test",
                },
                "fixture_contract": {
                    "path": fixture_ref,
                    "cases": [
                        {
                            "id": "empty-crc-zero",
                            "input_ref": "cases[0]",
                            "expected_ref": fixture_ref,
                        },
                        {
                            "id": "ascii-123456789-crc-zero",
                            "input_ref": "cases[1]",
                            "expected_ref": fixture_ref,
                        }
                    ],
                    "observable_outputs": ["return_code"],
                    "behavior_fields": ["return_code"],
                },
                "c_boundary": {
                    "functions": ["fdb_calc_crc32"],
                    "signatures": [
                        {
                            "function": "fdb_calc_crc32",
                            "return_type": "uint32_t",
                            "parameters": [
                                {"name": "crc", "c_type": "uint32_t", "direction": "input"},
                                {"name": "buf", "c_type": "const void*", "direction": "input"},
                                {"name": "size", "c_type": "size_t", "direction": "input"},
                            ],
                        }
                    ],
                },
                "non_goals": ["unit test only"],
            }
            spec_path = tmp_path / "real-fdb-calc-crc32-spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    sys.executable,
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            harness = (
                out_root
                / "flashdb"
                / "auto-translation"
                / "real-fdb-calc-crc32"
                / "l3-real-fdb-calc-crc32-c-oracle-harness-draft.c"
            ).read_text(encoding="utf-8")

            self.assertIn("static const uint8_t empty_crc_zero_buf[] = { 0 };", harness)
            self.assertIn("fixture cases: 2", harness)
            self.assertIn(
                'fixture case: ascii-123456789-crc-zero input_ref=cases[1] '
                f'expected_ref={fixture_ref} expected_outputs={{"return_code": 3421780262}}',
                harness,
            )
            self.assertIn(
                "static const uint8_t ascii_123456789_crc_zero_buf[] = "
                "{ 49u, 50u, 51u, 52u, 53u, 54u, 55u, 56u, 57u };",
                harness,
            )
            self.assertIn(
                "uint32_t actual_empty_crc_zero_return_code = "
                "fdb_calc_crc32((uint32_t)0u, empty_crc_zero_buf, (size_t)0u);",
                harness,
            )
            self.assertIn("if (actual_empty_crc_zero_return_code != (uint32_t)0u)", harness)
            self.assertIn(
                "uint32_t actual_ascii_123456789_crc_zero_return_code = "
                "fdb_calc_crc32((uint32_t)0u, ascii_123456789_crc_zero_buf, (size_t)9u);",
                harness,
            )
            self.assertIn(
                "if (actual_ascii_123456789_crc_zero_return_code != (uint32_t)3421780262u)",
                harness,
            )

    def test_rust_replay_draft_enumerates_bound_fixture_cases_without_semantic_claim(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            fixture_path = tmp_path / "real-fdb-calc-crc32.json"
            fixture_path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "empty-crc-zero",
                                "crc": 0,
                                "buf": [],
                                "size": 0,
                                "return_code": 0,
                            },
                            {
                                "id": "ascii-123456789-crc-zero",
                                "crc": 0,
                                "buf": [49, 50, 51, 52, 53, 54, 55, 56, 57],
                                "size": 9,
                                "return_code": 3421780262,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            fixture_ref = fixture_path.as_posix()
            spec = {
                "target_id": "flashdb",
                "slice_id": "real-fdb-calc-crc32",
                "source_commit": "1234567",
                "function_name": "fdb_calc_crc32",
                "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
                "fixture_hash": "real-fdb-calc-crc32-fixture",
                "build_profile": {
                    "include_paths": [],
                    "defines": [],
                    "compiler_command_source": "unit-test",
                },
                "fixture_contract": {
                    "path": fixture_ref,
                    "cases": [
                        {
                            "id": "empty-crc-zero",
                            "input_ref": "cases[0]",
                            "expected_ref": fixture_ref,
                        },
                        {
                            "id": "ascii-123456789-crc-zero",
                            "input_ref": "cases[1]",
                            "expected_ref": fixture_ref,
                        },
                    ],
                    "observable_outputs": ["return_code"],
                    "behavior_fields": ["return_code"],
                },
                "c_boundary": {
                    "functions": ["fdb_calc_crc32"],
                    "signatures": [
                        {
                            "function": "fdb_calc_crc32",
                            "return_type": "uint32_t",
                            "parameters": [
                                {"name": "crc", "c_type": "uint32_t", "direction": "input"},
                                {"name": "buf", "c_type": "const void*", "direction": "input"},
                                {"name": "size", "c_type": "size_t", "direction": "input"},
                            ],
                        }
                    ],
                },
                "non_goals": ["unit test only"],
            }
            spec_path = tmp_path / "real-fdb-calc-crc32-spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            subprocess.run(
                [
                    sys.executable,
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            evidence_dir = out_root / "flashdb" / "auto-translation" / "real-fdb-calc-crc32"
            replay_draft = (evidence_dir / "l3-real-fdb-calc-crc32-rust-replay-test-draft.rs").read_text(
                encoding="utf-8"
            )
            test_translation = json.loads(
                (evidence_dir / "l3-real-fdb-calc-crc32-test-translation-generated.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertIn('let _fixture = "' + fixture_ref + '";', replay_draft)
            self.assertIn('let _api = "fdb_calc_crc32";', replay_draft)
            self.assertIn("const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;", replay_draft)
            self.assertIn("struct FixtureCase", replay_draft)
            self.assertIn(
                'FixtureCase { id: "empty-crc-zero", crc: 0u32, buf: &[], size: 0usize, '
                "return_code: 0u32 }",
                replay_draft,
            )
            self.assertIn(
                'FixtureCase { id: "ascii-123456789-crc-zero", crc: 0u32, '
                "buf: &[49u8, 50u8, 51u8, 52u8, 53u8, 54u8, 55u8, 56u8, 57u8], "
                "size: 9usize, return_code: 3421780262u32 }",
                replay_draft,
            )
            self.assertIn('assert_eq!(fixture_cases.len(), 2usize, "fixture case count drifted");', replay_draft)
            self.assertIn(
                'assert_eq!(case.buf.len(), case.size, "{} fixture size must match byte buffer length", case.id);',
                replay_draft,
            )
            self.assertIn("let actual = fdb_calc_crc32(case.crc, case.buf, case.size);", replay_draft)
            self.assertIn("assert_eq!(actual, case.return_code", replay_draft)
            self.assertNotIn("TODO: call generated Rust API", replay_draft)
            self.assertNotIn("draft only: generated Rust API assertions are not bound", replay_draft)
            self.assertEqual(test_translation["status"], "recorded")
            self.assertFalse(test_translation["generated_draft_semantic_pass"])
            self.assertEqual(
                test_translation["source_test_inputs"]["fixtures"][0]["operation_count"],
                2,
            )
            self.assertEqual(test_translation["translation_mappings"][0]["status"], "mapped")

    def test_compile_success_records_harness_execution_without_oracle_claim(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            fake_bin = tmp_path / "fake-bin"
            fake_bin.mkdir()
            fake_cc_helper = fake_bin / "fake_cc.py"
            fake_cc_helper.write_text(
                "\n".join(
                    [
                        "import os",
                        "import shutil",
                        "import stat",
                        "import sys",
                        "",
                        "args = sys.argv[1:]",
                        "try:",
                        "    output = args[args.index('-o') + 1]",
                        "except (ValueError, IndexError):",
                        "    print('missing -o output', file=sys.stderr)",
                        "    sys.exit(2)",
                        "if os.name == 'nt':",
                        "    system_root = os.environ.get('SystemRoot') or os.environ.get('WINDIR') or r'C:\\Windows'",
                        "    zero_exit_exe = os.path.join(system_root, 'System32', 'hostname.exe')",
                        "    shutil.copyfile(zero_exit_exe, output)",
                        "else:",
                        "    with open(output, 'w', encoding='utf-8') as fh:",
                        "        fh.write('#!/bin/sh\\nexit 0\\n')",
                        "    os.chmod(output, os.stat(output).st_mode | stat.S_IXUSR)",
                        "print('fake cc compiled ' + output)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            if os.name == "nt":
                (fake_bin / "cc.cmd").write_text(
                    f'@echo off\r\n"{sys.executable}" "%~dp0fake_cc.py" %*\r\n',
                    encoding="utf-8",
                )
            else:
                fake_cc = fake_bin / "cc"
                fake_cc.write_text(
                    f'#!/bin/sh\nexec "{sys.executable}" "$(dirname "$0")/fake_cc.py" "$@"\n',
                    encoding="utf-8",
                )
                fake_cc.chmod(0o755)

            spec = {
                "target_id": "demo",
                "slice_id": "compile-run",
                "source_commit": "1234567",
                "function_name": "compile_run",
                "c_source": "int compile_run(void) { return 0; }",
                "fixture_hash": "fixture",
                "build_profile": {
                    "include_paths": [],
                    "defines": [],
                    "compiler_command_source": "unit-test",
                },
                "fixture_contract": {
                    "path": "unit-test-fixture.json",
                    "behavior_fields": ["return_code"],
                },
                "c_boundary": {
                    "functions": ["compile_run"],
                    "signatures": [
                        {
                            "function": "compile_run",
                            "return_type": "int",
                            "parameters": [],
                        }
                    ],
                },
                "non_goals": ["unit test only"],
            }
            spec_path = tmp_path / "compile-run.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"
            env = os.environ.copy()
            env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")

            result = subprocess.run(
                [
                    sys.executable,
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            oracle_status = json.loads(
                (
                    out_root
                    / "demo"
                    / "auto-translation"
                    / "compile-run"
                    / "l3-compile-run-c-oracle-status.json"
                ).read_text(encoding="utf-8")
            )

            self.assertEqual(oracle_status["status"], "DRAFT_GENERATED")
            self.assertEqual(oracle_status["toolchain_status"], "COMPILE_SUCCEEDED_NOT_ORACLE")
            self.assertFalse(oracle_status["semantic_pass"])
            self.assertEqual(oracle_status["compile_execution"]["status"], "compile_succeeded_not_oracle")
            self.assertEqual(
                oracle_status["compile_execution"]["toolchain_status_after_attempt"],
                "COMPILE_SUCCEEDED_NOT_ORACLE",
            )
            self.assertFalse(oracle_status["compile_execution"]["semantic_pass"])
            harness_execution = oracle_status["compile_execution"]["harness_execution"]
            executable_path = str(
                out_root
                / "demo"
                / "auto-translation"
                / "compile-run"
                / "l3-compile-run-c-oracle-harness-draft.exe"
            ).replace("\\", "/")
            self.assertEqual(harness_execution["status"], "exited_zero_not_oracle")
            self.assertTrue(harness_execution["attempted"])
            self.assertEqual(harness_execution["argv"], [executable_path])
            self.assertEqual(
                harness_execution["working_directory"],
                str(out_root / "demo" / "auto-translation" / "compile-run").replace("\\", "/"),
            )
            self.assertEqual(harness_execution["executable_path"], executable_path)
            self.assertEqual(harness_execution["timeout_seconds"], 30)
            self.assertFalse(harness_execution["semantic_pass"])
            self.assertEqual(harness_execution["returncode"], 0)
            self.assertIsInstance(harness_execution["stdout"], str)
            self.assertIsInstance(harness_execution["stderr"], str)
            self.assertEqual(
                harness_execution["diagnostics"],
                ["C oracle harness executed, but execution output has not passed oracle diff gates."],
            )
            self.assertEqual(harness_execution["output_gate"]["status"], "unsupported_not_oracle")
            self.assertFalse(harness_execution["output_gate"]["semantic_pass"])
            self.assertEqual(harness_execution["output_gate"]["expected_stdout_fragments"], [])

    def test_cc_compile_command_falls_back_to_gcc_when_cc_is_missing(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            fake_bin = tmp_path / "fake-bin"
            fake_bin.mkdir()
            fake_cc_helper = fake_bin / "fake_cc.py"
            fake_cc_helper.write_text(
                "\n".join(
                    [
                        "import os",
                        "import shutil",
                        "import stat",
                        "import sys",
                        "",
                        "args = sys.argv[1:]",
                        "try:",
                        "    output = args[args.index('-o') + 1]",
                        "except (ValueError, IndexError):",
                        "    print('missing -o output', file=sys.stderr)",
                        "    sys.exit(2)",
                        "if os.name == 'nt':",
                        "    system_root = os.environ.get('SystemRoot') or os.environ.get('WINDIR') or r'C:\\Windows'",
                        "    zero_exit_exe = os.path.join(system_root, 'System32', 'hostname.exe')",
                        "    shutil.copyfile(zero_exit_exe, output)",
                        "else:",
                        "    with open(output, 'w', encoding='utf-8') as fh:",
                        "        fh.write('#!/bin/sh\\nexit 0\\n')",
                        "    os.chmod(output, os.stat(output).st_mode | stat.S_IXUSR)",
                        "print('fake gcc compiled ' + output)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            if os.name == "nt":
                fake_gcc = fake_bin / "gcc.cmd"
                fake_gcc.write_text(
                    f'@echo off\r\n"{sys.executable}" "%~dp0fake_cc.py" %*\r\n',
                    encoding="utf-8",
                )
            else:
                fake_gcc = fake_bin / "gcc"
                fake_gcc.write_text(
                    f'#!/bin/sh\nexec "{sys.executable}" "$(dirname "$0")/fake_cc.py" "$@"\n',
                    encoding="utf-8",
                )
                fake_gcc.chmod(0o755)

            evidence_dir = tmp_path / "evidence"
            evidence_dir.mkdir()
            harness_name = "l3-compile-run-gcc-c-oracle-harness-draft.c"
            output_name = "l3-compile-run-gcc-c-oracle-harness-draft.exe"
            (evidence_dir / harness_name).write_text("int main(void) { return 0; }\n", encoding="utf-8")
            compile_command = {
                "argv": ["cc", harness_name, "-o", output_name],
                "working_directory": evidence_dir.as_posix(),
            }

            def fake_which(name: str) -> str | None:
                if name == "gcc":
                    return str(fake_gcc)
                return None

            with mock.patch.object(module.shutil, "which", side_effect=fake_which):
                compile_execution = module.c_oracle_compile_execution(
                    compile_command, evidence_dir, False, None, None
                )

            self.assertEqual(compile_execution["status"], "compile_succeeded_not_oracle")
            self.assertEqual(compile_execution["compiler_name"], "gcc")
            self.assertIn("gcc", Path(compile_execution["compiler_path"]).name)
            self.assertIn("harness_execution", compile_execution)
            self.assertEqual(compile_execution["toolchain_adapter"], "local")
            self.assertFalse(compile_execution["semantic_pass"])

    def test_build_profile_link_source_files_extend_c_oracle_compile_command(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            harness_path = evidence_dir / "l3-link-only-c-oracle-harness-draft.c"
            spec = {
                "source": {"source_root": "unit"},
                "build_profile": {
                    "include_paths": [],
                    "defines": [],
                    "link_source_files": [
                        {
                            "path": "link.c",
                            "role": "link_dependency",
                            "sha256": "link-sha",
                        }
                    ],
                },
                "c_boundary": {
                    "files": [
                        {
                            "path": "entry.c",
                            "role": "source",
                            "sha256": "entry-sha",
                        }
                    ],
                },
            }

            compile_command = module.c_oracle_compile_command(spec, harness_path, evidence_dir)

            self.assertEqual(
                compile_command["link_source_files"],
                [
                    {
                        "path": "entry.c",
                        "resolved_path": "unit/entry.c",
                        "role": "source",
                        "sha256": "entry-sha",
                        "resolution": "source_root_relative",
                    },
                    {
                        "path": "link.c",
                        "resolved_path": "unit/link.c",
                        "role": "link_dependency",
                        "sha256": "link-sha",
                        "resolution": "source_root_relative",
                    },
                ],
            )
            self.assertEqual(
                compile_command["link_strategy"],
                "compile_harness_with_declared_c_boundary_and_build_profile_sources",
            )
            self.assertIn("unit/link.c", compile_command["argv"])

    def test_cc_compile_command_uses_wsl_adapter_when_local_candidates_are_missing(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            output_name = "l3-wsl-c-oracle-harness-draft.exe"
            compile_command = {
                "argv": [
                    "cc",
                    "-std=c99",
                    "-IC:/src/include",
                    "l3-wsl-c-oracle-harness-draft.c",
                    "C:/src/unit.c",
                    "-o",
                    output_name,
                ],
                "working_directory": evidence_dir.as_posix(),
            }
            wsl_launcher = "C:/Windows/System32/wsl.exe"
            calls: list[list[str]] = []

            def fake_which(name: str) -> str | None:
                if name in {"wsl.exe", "wsl"}:
                    return wsl_launcher
                return None

            def fake_wsl_path(path: Path, launcher: str) -> str:
                self.assertEqual(launcher, wsl_launcher)
                text = str(path).replace("\\", "/")
                if text == "C:/src/include":
                    return "/mnt/c/src/include"
                if text == "C:/src/unit.c":
                    return "/mnt/c/src/unit.c"
                if text.endswith(output_name):
                    return f"/mnt/fake/evidence/{output_name}"
                return "/mnt/fake/evidence"

            def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
                calls.append(args)
                command = args[-1] if args[:3] == [wsl_launcher, "-e", "sh"] else ""
                if "command -v cc" in command:
                    return subprocess.CompletedProcess(args, 0, "/usr/bin/cc\n", "")
                if "/usr/bin/cc" in command:
                    (evidence_dir / output_name).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                    return subprocess.CompletedProcess(args, 0, "compiled\n", "")
                if output_name in command:
                    return subprocess.CompletedProcess(args, 0, "harness stdout\n", "")
                return subprocess.CompletedProcess(args, 127, "", "unexpected command")

            with (
                mock.patch.object(module.shutil, "which", side_effect=fake_which),
                mock.patch.object(module, "wsl_path", side_effect=fake_wsl_path),
                mock.patch.object(module.subprocess, "run", side_effect=fake_run),
            ):
                compile_execution = module.c_oracle_compile_execution(
                    compile_command, evidence_dir, False, None, None
                )

            self.assertEqual(compile_execution["status"], "compile_succeeded_not_oracle")
            self.assertEqual(compile_execution["compiler_name"], "cc")
            self.assertEqual(compile_execution["compiler_path"], "/usr/bin/cc")
            self.assertEqual(compile_execution["toolchain_adapter"], "wsl")
            self.assertEqual(compile_execution["argv"], compile_command["argv"])
            self.assertIn("-I/mnt/c/src/include", compile_execution["execution_argv"][-1])
            self.assertIn("/mnt/c/src/unit.c", compile_execution["execution_argv"][-1])
            harness_execution = compile_execution["harness_execution"]
            self.assertEqual(harness_execution["status"], "exited_zero_not_oracle")
            self.assertEqual(harness_execution["toolchain_adapter"], "wsl")
            self.assertEqual(harness_execution["execution_argv"][0], wsl_launcher)
            self.assertEqual(harness_execution["output_gate"]["status"], "unsupported_not_oracle")
            self.assertGreaterEqual(len(calls), 3)

    def test_compile_execution_argv_resolves_evidence_and_repo_relative_paths(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            harness_path = evidence_dir / "harness.c"
            harness_path.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            output_path = evidence_dir / "harness.exe"
            compile_command = [
                "cc",
                "-std=c99",
                "-Ivalidation",
                "harness.c",
                "validation/tools/auto_migrate.py",
                "-o",
                "harness.exe",
            ]
            compiler_resolution = {
                "path": "C:/tools/cc.exe",
                "name": "cc",
                "candidates": ["cc"],
                "adapter": "local",
                "launcher": None,
            }

            execution_argv = module.c_oracle_compile_execution_argv(
                compile_command, evidence_dir, compiler_resolution
            )

            self.assertEqual(execution_argv[0], "C:/tools/cc.exe")
            self.assertIn(f"-I{REPO_ROOT / 'validation'}", execution_argv)
            self.assertIn(str(harness_path), execution_argv)
            self.assertIn(str(REPO_ROOT / "validation" / "tools" / "auto_migrate.py"), execution_argv)
            self.assertIn(str(output_path), execution_argv)

    def test_compile_execution_argv_resolves_relative_evidence_directory_to_absolute_paths(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-relative-evidence-", dir=REPO_ROOT) as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            harness_path = evidence_dir / "harness.c"
            harness_path.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            relative_evidence_dir = evidence_dir.relative_to(REPO_ROOT)

            resolved = module.c_oracle_compile_execution_args_with_resolved_paths(
                ["cc", "harness.c", "-o", "harness.exe"],
                relative_evidence_dir,
            )

            self.assertIn(str(harness_path), resolved)
            self.assertIn(str(evidence_dir / "harness.exe"), resolved)
            self.assertNotIn(str(relative_evidence_dir / "harness.c"), resolved)

    def test_c_oracle_compile_execution_handles_missing_subprocess_streams(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            (evidence_dir / "harness.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
            compile_command = {
                "argv": ["cc", "harness.c", "-o", "harness.exe"],
                "working_directory": evidence_dir.as_posix(),
            }

            def fake_which(name: str) -> str | None:
                if name == "cc":
                    return "C:/tools/cc.exe"
                return None

            def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
                self.assertEqual(kwargs["encoding"], "utf-8")
                self.assertEqual(kwargs["errors"], "replace")
                return subprocess.CompletedProcess(args, 1, None, None)

            with (
                mock.patch.object(module.shutil, "which", side_effect=fake_which),
                mock.patch.object(module.subprocess, "run", side_effect=fake_run),
            ):
                compile_execution = module.c_oracle_compile_execution(
                    compile_command, evidence_dir, False, None, None
                )

            self.assertEqual(compile_execution["status"], "compile_failed")
            self.assertEqual(compile_execution["stdout"], "")
            self.assertEqual(compile_execution["stderr"], "")
            self.assertIn("C oracle compile command failed", compile_execution["diagnostics"][0])

    def test_capability_ledger_records_c_oracle_matched_not_oracle_without_semantic_claim(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "target_id": "flashdb",
            "slice_id": "real-fdb-blob-make",
            "source_commit": "1234567",
        }
        route_decision = {
            "level": "L1",
            "status": "recorded",
            "translator": {"candidate_generation_allowed": True},
        }
        validation_profile = {"generated_draft_semantic_pass": False}
        c_oracle = {
            "compile_execution": {
                "status": "compile_succeeded_not_oracle",
                "harness_execution": {
                    "status": "exited_zero_not_oracle",
                    "output_gate": {
                        "status": "matched_not_oracle",
                        "matched_stdout_fragments": [
                            "fixture case null-empty return_same_blob matched",
                        ],
                        "missing_stdout_fragments": [],
                    },
                },
            }
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-capability-ledger-") as tmp:
            evidence_dir = Path(tmp)

            payload = module.emit_capability_delta_ledger(
                spec,
                evidence_dir,
                route_decision,
                validation_profile,
                c_oracle=c_oracle,
            )

            c_oracle_delta = next(
                item
                for item in payload["capability_delta"]
                if item["construct_id"] == "c_oracle_harness_matched_not_oracle"
            )
            self.assertEqual(payload["source_commit"], "1234567")
            self.assertEqual(payload["source_identity"]["source_commit"], "1234567")
            self.assertEqual(c_oracle_delta["kind"], "candidate_verification")
            self.assertEqual(c_oracle_delta["generated_candidate_status"], "candidate")
            self.assertFalse(c_oracle_delta["semantic_pass"])
            self.assertTrue(c_oracle_delta["negative_coverage"])

    def test_wsl_path_failure_records_structured_compile_failure(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            compile_command = {
                "argv": ["cc", "-IC:/src/include", "harness.c", "-o", "harness.exe"],
                "working_directory": evidence_dir.as_posix(),
            }
            wsl_launcher = "C:/Windows/System32/wsl.exe"

            def fake_which(name: str) -> str | None:
                if name in {"wsl.exe", "wsl"}:
                    return wsl_launcher
                return None

            def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
                command = args[-1] if args[:3] == [wsl_launcher, "-e", "sh"] else ""
                if "command -v cc" in command:
                    return subprocess.CompletedProcess(args, 0, "/usr/bin/cc\n", "")
                if args[:3] == [wsl_launcher, "-e", "wslpath"]:
                    return subprocess.CompletedProcess(args, 1, "", "wslpath failed")
                return subprocess.CompletedProcess(args, 127, "", "unexpected command")

            with (
                mock.patch.object(module.shutil, "which", side_effect=fake_which),
                mock.patch.object(module.subprocess, "run", side_effect=fake_run),
            ):
                compile_execution = module.c_oracle_compile_execution(
                    compile_command, evidence_dir, False, None, None
                )

            self.assertEqual(compile_execution["status"], "compile_failed")
            self.assertTrue(compile_execution["attempted"])
            self.assertFalse(compile_execution["semantic_pass"])
            self.assertEqual(compile_execution["toolchain_adapter"], "wsl")
            self.assertEqual(compile_execution["execution_argv"], [])
            self.assertEqual(compile_execution["toolchain_status_after_attempt"], "COMPILE_FAILED")
            self.assertIn("wslpath failed", compile_execution["stderr"])

    def test_wsl_path_timeout_records_structured_compile_timeout(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            compile_command = {
                "argv": ["cc", "-IC:/src/include", "harness.c", "-o", "harness.exe"],
                "working_directory": evidence_dir.as_posix(),
            }
            wsl_launcher = "C:/Windows/System32/wsl.exe"

            def fake_which(name: str) -> str | None:
                if name in {"wsl.exe", "wsl"}:
                    return wsl_launcher
                return None

            def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
                command = args[-1] if args[:3] == [wsl_launcher, "-e", "sh"] else ""
                if "command -v cc" in command:
                    return subprocess.CompletedProcess(args, 0, "/usr/bin/cc\n", "")
                if args[:3] == [wsl_launcher, "-e", "wslpath"]:
                    raise subprocess.TimeoutExpired(args, 10, output="", stderr="wslpath timed out")
                return subprocess.CompletedProcess(args, 127, "", "unexpected command")

            with (
                mock.patch.object(module.shutil, "which", side_effect=fake_which),
                mock.patch.object(module.subprocess, "run", side_effect=fake_run),
            ):
                compile_execution = module.c_oracle_compile_execution(
                    compile_command, evidence_dir, False, None, None
                )

            self.assertEqual(compile_execution["status"], "compile_timeout")
            self.assertTrue(compile_execution["attempted"])
            self.assertFalse(compile_execution["semantic_pass"])
            self.assertEqual(compile_execution["toolchain_adapter"], "wsl")
            self.assertEqual(compile_execution["execution_argv"], [])
            self.assertEqual(compile_execution["toolchain_status_after_attempt"], "COMPILE_FAILED")

    def test_harness_output_gate_matches_fixture_stdout_without_oracle_claim(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            fixture_path = Path(tmp) / "real-fdb-calc-crc32.json"
            fixture_path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "empty-crc-zero",
                                "crc": 0,
                                "buf": [],
                                "size": 0,
                                "return_code": 0,
                            },
                            {
                                "id": "ascii-123456789-crc-zero",
                                "crc": 0,
                                "buf": [49, 50, 51, 52, 53, 54, 55, 56, 57],
                                "size": 9,
                                "return_code": 3421780262,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            fixture_ref = fixture_path.as_posix()
            spec = {
                "target_id": "flashdb",
                "slice_id": "real-fdb-calc-crc32",
                "source_commit": "1234567",
                "function_name": "fdb_calc_crc32",
                "fixture_hash": "real-fdb-calc-crc32-fixture",
                "fixture_contract": {
                    "path": fixture_ref,
                    "cases": [
                        {
                            "id": "empty-crc-zero",
                            "input_ref": "cases[0]",
                            "expected_ref": fixture_ref,
                        },
                        {
                            "id": "ascii-123456789-crc-zero",
                            "input_ref": "cases[1]",
                            "expected_ref": fixture_ref,
                        },
                    ],
                    "observable_outputs": ["return_code"],
                    "behavior_fields": ["return_code"],
                },
            }
            fixture_binding = module.oracle_fixture_binding(spec)
            harness_execution = {
                "status": "exited_zero_not_oracle",
                "returncode": 0,
                "stdout": "\n".join(
                    [
                        "oracle harness draft for fdb_calc_crc32",
                        f"fixture input: {fixture_ref}",
                        "fixture case empty-crc-zero return_code matched",
                        "fixture case ascii-123456789-crc-zero return_code matched",
                    ]
                )
                + "\n",
                "stderr": "",
            }

            output_gate = module.c_oracle_harness_output_gate(spec, fixture_binding, harness_execution)

            self.assertEqual(output_gate["status"], "matched_not_oracle")
            self.assertFalse(output_gate["semantic_pass"])
            self.assertEqual(output_gate["gate"], "c_oracle_harness_output")
            self.assertEqual(output_gate["compared_fields"], ["return_code"])
            self.assertEqual(output_gate["fixture_expected_output_status"], "declared_not_executed")
            self.assertEqual(
                output_gate["expected_stdout_fragments"],
                [
                    "fixture case empty-crc-zero return_code matched",
                    "fixture case ascii-123456789-crc-zero return_code matched",
                ],
            )
            self.assertEqual(
                output_gate["matched_stdout_fragments"],
                output_gate["expected_stdout_fragments"],
            )
            self.assertEqual(output_gate["missing_stdout_fragments"], [])
            self.assertEqual(
                output_gate["diagnostics"],
                [
                    "C oracle harness stdout matched draft fixture markers, but oracle diff gates are still required."
                ],
            )

    def test_harness_output_gate_uses_raw_stdout_before_report_truncation(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            script_path = tmp_path / ("harness.cmd" if os.name == "nt" else "harness")
            marker = "fixture case empty-crc-zero return_code matched"
            if os.name == "nt":
                script_path.write_text(
                    "@echo off\r\n"
                    f'"{sys.executable}" -c "print(\'x\' * 5000); print({marker!r})"\r\n',
                    encoding="utf-8",
                )
            else:
                script_path.write_text(
                    "#!/bin/sh\n"
                    f"'{sys.executable}' -c \"print('x' * 5000); print({marker!r})\"\n",
                    encoding="utf-8",
                )
                script_path.chmod(0o755)
            spec = {
                "fixture_contract": {
                    "path": "unit-test-fixture.json",
                    "cases": [
                        {
                            "id": "empty-crc-zero",
                            "input_ref": "cases[0]",
                            "expected_ref": "inline",
                            "expected_outputs": {"return_code": 0},
                        }
                    ],
                    "observable_outputs": ["return_code"],
                    "behavior_fields": ["return_code"],
                }
            }
            fixture_binding = module.oracle_fixture_binding(spec)

            harness_execution = module.c_oracle_harness_execution(
                ["cc", "-o", script_path.as_posix()],
                tmp_path,
                spec,
                fixture_binding,
            )

            self.assertEqual(harness_execution["status"], "exited_zero_not_oracle")
            self.assertIn("...[truncated]", harness_execution["stdout"])
            self.assertNotIn(marker, harness_execution["stdout"])
            self.assertEqual(harness_execution["output_gate"]["status"], "matched_not_oracle")
            self.assertEqual(harness_execution["output_gate"]["matched_stdout_fragments"], [marker])

    def test_generated_candidate_diff_records_matched_diagnostic_without_semantic_claim(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            evidence_dir = tmp_path / "evidence"
            evidence_dir.mkdir()
            fixture_path = tmp_path / "fixture.json"
            fixture_path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "case-zero",
                                "crc": 0,
                                "buf": [],
                                "size": 0,
                                "return_code": 0,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            fixture_ref = fixture_path.as_posix()
            spec = {
                "target_id": "demo",
                "slice_id": "candidate-diff",
                "source_commit": "1234567",
                "function_name": "candidate_diff",
                "fixture_hash": "fixture",
                "fixture_contract": {
                    "path": fixture_ref,
                    "cases": [
                        {
                            "id": "case-zero",
                            "input_ref": "cases[0]",
                            "expected_ref": fixture_ref,
                        }
                    ],
                    "observable_outputs": ["return_code"],
                    "behavior_fields": ["return_code"],
                },
            }
            spec_path = tmp_path / "slice-spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            (evidence_dir / "l3-candidate-diff-rust-draft.rs").write_text(
                "pub fn candidate_diff() -> i32 { 0 }\n",
                encoding="utf-8",
            )
            (evidence_dir / "l3-candidate-diff-translator-input.json").write_text(
                json.dumps({"slice_id": "candidate-diff"}),
                encoding="utf-8",
            )
            fixture_binding = module.oracle_fixture_binding(spec)
            output_gate = module.c_oracle_harness_output_gate(
                spec,
                fixture_binding,
                {
                    "status": "exited_zero_not_oracle",
                    "returncode": 0,
                    "stdout": "fixture case case-zero return_code matched\n",
                },
            )
            module.write_l3_candidate_supporting_evidence(
                spec,
                evidence_dir,
                spec_path,
                oracle={
                    "status": "DRAFT_GENERATED",
                    "semantic_pass": False,
                    "toolchain_status": "COMPILE_SUCCEEDED_NOT_ORACLE",
                    "compile_execution": {
                        "status": "compile_succeeded_not_oracle",
                        "harness_execution": {
                            "status": "exited_zero_not_oracle",
                            "returncode": 0,
                            "output_gate": output_gate,
                        }
                    },
                },
                replay={
                    "status": "passed",
                    "generated_draft_replay_pass": True,
                    "generated_draft_semantic_pass": False,
                    "replay_execution": {"status": "passed"},
                },
                rust_check={"status": "passed"},
                cache={"status": "recorded"},
                c2rust_baseline={"status": "generated"},
                route_decision={"status": "candidate_generated", "level": "L3", "translator": {"kind": "tier1"}},
                validation_profile={"status": "incomplete", "skipped_gates": []},
            )

            diff = json.loads((evidence_dir / "l3-candidate-diff-diff.json").read_text(encoding="utf-8"))

            self.assertEqual(diff["status"], "incomplete")
            self.assertFalse(diff["semantic_pass"])
            self.assertEqual(diff["blocked_by"], ["accepted_c_oracle"])
            self.assertTrue(diff["generated_candidate_diff_pass"])
            self.assertEqual(diff["reason_code"], "candidate_matched_accepted_oracle_required")
            self.assertEqual(
                diff["candidate_diff"],
                {
                    "schema_version": 1,
                    "status": "matched_not_oracle",
                    "semantic_pass": False,
                    "compared_fields": ["return_code"],
                    "c_oracle_output_gate_status": "matched_not_oracle",
                    "rust_replay_status": "passed",
                    "matched_stdout_fragments": ["fixture case case-zero return_code matched"],
                    "missing_stdout_fragments": [],
                    "boundary": "Generated candidate diff is diagnostic only until accepted oracle diff gates pass.",
                },
            )

    def test_generated_candidate_diff_requires_matched_oracle_output_gate(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "fixture_contract": {
                "observable_outputs": ["return_code"],
                "behavior_fields": ["return_code"],
            }
        }
        replay = {
            "status": "passed",
            "generated_draft_replay_pass": True,
            "generated_draft_semantic_pass": False,
        }
        oracle = {
            "status": "DRAFT_GENERATED",
            "semantic_pass": False,
            "toolchain_status": "COMPILE_SUCCEEDED_NOT_ORACLE",
            "compile_execution": {
                "status": "compile_succeeded_not_oracle",
                "harness_execution": {
                    "status": "exited_zero_not_oracle",
                    "output_gate": {
                        "status": "mismatch_not_oracle",
                        "semantic_pass": False,
                        "compared_fields": ["return_code"],
                        "matched_stdout_fragments": [],
                        "missing_stdout_fragments": ["fixture case case-zero return_code matched"],
                    },
                },
            },
        }

        self.assertIsNone(module.generated_candidate_diff_from_diagnostics(spec, oracle, replay, "passed"))

    def test_route_baseline_and_validation_profile_evidence_are_emitted(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "route-profile",
            "source_commit": "1234567",
            "function_name": "route_profile",
            "c_source": "int route_profile(int value) { return value + 1; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "path": "unit-test-fixture.json",
                "behavior_fields": ["return_code"],
                "scalar_input_domain": {
                    "case_source": "unit-test",
                    "parameters": [
                        {
                            "name": "value",
                            "type": "int32",
                            "range": [-128, 127],
                            "excludes": [],
                        }
                    ],
                    "covers_overflow_boundaries": False,
                },
            },
            "c_boundary": {
                "scalar_arithmetic_contract": {
                    "wrapping_profile": "not_declared",
                    "signed_overflow": "runtime_precondition_no_overflow",
                    "division_by_zero": "runtime_precondition_nonzero_divisor",
                    "signed_division_overflow": "runtime_precondition_excludes_min_div_minus_one",
                    "shift_count": "runtime_precondition_in_range",
                    "signed_right_shift": "fail_closed_without_explicit_contract",
                },
            },
            "claim_boundary": {
                "must_not_claim": [
                    "signed overflow equivalence outside the declared scalar input domain",
                    "signed right shift equivalence without an explicit implementation-defined contract",
                ],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "route-profile.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "route-profile"
            baseline = json.loads(
                (evidence_dir / "l3-route-profile-c2rust-baseline-manifest.json").read_text(encoding="utf-8")
            )
            route = json.loads((evidence_dir / "l3-route-profile-route-decision.json").read_text(encoding="utf-8"))
            profile = json.loads(
                (evidence_dir / "l3-route-profile-validation-profile.json").read_text(encoding="utf-8")
            )
            l3 = json.loads((evidence_dir / "l3-route-profile-evidence-manifest.json").read_text(encoding="utf-8"))
            final = json.loads((evidence_dir / "l3-route-profile-final-verification.json").read_text(encoding="utf-8"))
            plan = json.loads((evidence_dir / "l3-route-profile-auto-translation-plan.json").read_text(encoding="utf-8"))
            cache = json.loads((evidence_dir / "l3-route-profile-auto-cache-metadata.json").read_text(encoding="utf-8"))
            diff = json.loads((evidence_dir / "l3-route-profile-diff.json").read_text(encoding="utf-8"))
            negative = json.loads((evidence_dir / "l3-route-profile-negative-diff.json").read_text(encoding="utf-8"))
            replay_draft = (evidence_dir / "l3-route-profile-rust-replay-test-draft.rs").read_text(encoding="utf-8")

            self.assertEqual(profile["competition_environment"]["profile_id"], "huawei-competition-ubuntu-24.04")
            self.assertEqual(profile["competition_environment"]["path"], "config/competition-env/environment.json")
            self.assertRegex(profile["competition_environment"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                cache["competition_environment_identity"],
                profile["competition_environment"],
            )
            self.assertIn("competition_environment_identity", cache["cache_input_fields"])
            self.assertIn(baseline["status"], {"generated", "skipped", "blocked"})
            self.assertEqual(baseline["correctness_role"], "candidate_context_only")
            self.assertEqual(route["level"], "L0")
            self.assertEqual(route["translator"]["kind"], "tier1")
            self.assertEqual(
                route["scalar_ub_contract"]["c_boundary"]["signed_overflow"],
                "runtime_precondition_no_overflow",
            )
            self.assertEqual(
                route["scalar_ub_contract"]["fixture_contract"]["parameters"][0]["name"],
                "value",
            )
            self.assertIn(
                "signed right shift equivalence without an explicit implementation-defined contract",
                route["scalar_ub_contract"]["claim_boundary"]["must_not_claim"],
            )
            self.assertIn("compile", profile["required_gates"])
            self.assertIn("c_oracle_diff", profile["required_gates"])
            self.assertEqual(profile["scalar_ub_contract"], route["scalar_ub_contract"])
            self.assertEqual(profile["loop_policy"]["source"], "run_policy")
            self.assertEqual(
                Path(manifest["c2rust_baseline"]["path"]).name,
                "l3-route-profile-c2rust-baseline-manifest.json",
            )
            self.assertEqual(manifest["fixture"]["path"], "unit-test-fixture.json")
            self.assertIn('let _fixture = "unit-test-fixture.json";', replay_draft)
            self.assertTrue((evidence_dir / "l3-route-profile-c2rust-baseline-manifest.json").exists())
            self.assertEqual(manifest["route_decision"]["level"], "L0")
            self.assertEqual(manifest["validation_profile"]["profile"], "L0-dev")
            self.assertIn("c2rust_baseline", l3["evidence"])
            self.assertIn("route_decision", l3["evidence"])
            self.assertIn("validation_profile", l3["evidence"])
            self.assertEqual(
                Path(final["c2rust_baseline"]["path"]).name,
                "l3-route-profile-c2rust-baseline-manifest.json",
            )
            self.assertEqual(final["validation_profile_status"], profile["status"])
            self.assertEqual(Path(plan["route_decision"]["path"]).name, "l3-route-profile-route-decision.json")
            self.assertEqual(
                Path(cache["dependent_artifacts"]["c2rust_baseline"]["path"]).name,
                "l3-route-profile-c2rust-baseline-manifest.json",
            )
            self.assertIn("route_decision_identity", cache["cache_input_fields"])
            self.assertIn("scalar_ub_contract_identity", cache["cache_input_fields"])
            self.assertIn("oracle_boundary_contract_identity", cache["cache_input_fields"])
            self.assertEqual(
                cache["scalar_ub_contract_identity"]["status"],
                "recorded",
            )
            self.assertEqual(
                cache["oracle_boundary_contract_identity"]["status"],
                profile["oracle_boundary_contract"]["status"],
            )
            self.assertEqual(diff["diff_gate"], "schema_aware_c_rust_diff")
            self.assertEqual(diff["status"], "incomplete")
            self.assertFalse(diff["semantic_pass"])
            self.assertEqual(diff["compared_fields"], ["return_code"])
            self.assertTrue(diff["accepted_diff_required"])
            self.assertEqual(diff["blocked_by"], ["c_oracle", "rust_replay"])
            self.assertEqual(diff["required_inputs"]["c_oracle_required_status"], "C_ORACLE_GENERATED")
            self.assertEqual(diff["required_inputs"]["rust_report_required_status"], "passed")
            self.assertEqual(negative["negative_diff_gate"], "schema_aware_negative_diff")
            self.assertEqual(negative["status"], "incomplete")
            self.assertTrue(negative["expected_failure"])
            self.assertFalse(negative["mutation_detected"])
            self.assertEqual(negative["blocked_by"], ["schema_diff"])
            self.assertEqual(negative["required_inputs"]["schema_diff_required_status"], "passed")

    def test_route_and_profile_bind_clang_lowered_typed_ir_candidate_evidence(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "target_id": "flashdb",
            "slice_id": "real-fdb-calc-crc32",
            "source_commit": "93d1755",
            "function_name": "fdb_calc_crc32",
            "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
            "fixture_hash": "fixture",
            "build_profile": {"compiler_command_source": "unit-test"},
            "fixture_contract": {
                "scalar_input_domain": {
                    "case_source": "unit-test",
                    "parameters": [
                        {
                            "name": "size",
                            "type": "size_t",
                            "range": [0, 1024],
                            "excludes": [],
                        }
                    ],
                    "covers_overflow_boundaries": False,
                },
            },
            "c_boundary": {
                "scalar_arithmetic_contract": {
                    "wrapping_profile": "not_declared",
                    "signed_overflow": "runtime_precondition_no_overflow",
                    "division_by_zero": "runtime_precondition_nonzero_divisor",
                    "signed_division_overflow": "runtime_precondition_excludes_min_div_minus_one",
                    "shift_count": "runtime_precondition_in_range",
                    "signed_right_shift": "fail_closed_without_explicit_contract",
                },
            },
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-real-fdb-calc-crc32"
            (evidence_dir / f"{prefix}-type-map.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-cfg.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-pointer-graph.json").write_text(
                json.dumps(
                    {
                        "status": "recorded",
                        "pointer_nodes": [
                            {
                                "id": "buf",
                                "ownership_role": "borrowed_input",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (evidence_dir / f"{prefix}-auto-translation-plan.json").write_text(
                json.dumps({"status": "draft_generated"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-test-translation-generated.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-clang-lowering-report.json").write_text(
                json.dumps(
                    {
                        "status": "lowered",
                        "typed_ir_candidate": {
                            "status": "generated",
                            "candidate_route": {
                                "route_id": "generic-typed-ir",
                                "route": "GenericTypedIr",
                                "candidate_generator": "GenericTypedIrEmitter",
                                "token_cost": 0,
                                "deprecated": False,
                            },
                            "readonly_globals": [
                                {
                                    "name": "crc32_table",
                                    "array_len": 256,
                                    "init_kind": "integer_array",
                                    "value_count": 256,
                                }
                            ],
                            "runtime_preconditions": [
                                {
                                    "code": "shift_count_in_range",
                                    "detail": "shift count must stay within the lhs integer width",
                                    "ir_node": "IrExpr::Binary.Shl",
                                    "source_span": None,
                                }
                            ],
                            "rust_draft_generated": True,
                            "semantic_pass": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            c2rust_baseline = {"status": "generated", "correctness_role": "candidate_context_only"}
            route = module.emit_route_decision(spec, evidence_dir, {"status": "generated"}, c2rust_baseline)
            profile = module.emit_validation_profile(
                spec,
                evidence_dir,
                route,
                {"status": "DRAFT_GENERATED"},
                {"status": "passed"},
            )

            typed_ir = route["candidate_generation"]["typed_ir"]
            self.assertEqual(route["source_commit"], "93d1755")
            self.assertEqual(profile["source_commit"], "93d1755")
            self.assertEqual(route["source_identity"]["source_commit"], "93d1755")
            self.assertEqual(profile["source_identity"], route["source_identity"])
            self.assertEqual(typed_ir["status"], "generated")
            self.assertEqual(
                Path(route["source_artifacts"]["clang_lowering_report"]["path"]).name,
                f"{prefix}-clang-lowering-report.json",
            )
            self.assertEqual(Path(typed_ir["source_artifact"]["path"]).name, f"{prefix}-clang-lowering-report.json")
            self.assertEqual(typed_ir["source_artifact"]["status"], "lowered")
            self.assertIn("sha256", typed_ir["source_artifact"])
            self.assertEqual(typed_ir["candidate_route"]["route"], "GenericTypedIr")
            self.assertEqual(route["level"], "L1")
            self.assertEqual(route["verification_profile"], "L1-dev")
            self.assertEqual(typed_ir["readonly_globals_identity"]["count"], 1)
            self.assertEqual(typed_ir["readonly_globals_identity"]["names"], ["crc32_table"])
            self.assertEqual(typed_ir["readonly_globals"][0]["name"], "crc32_table")
            self.assertEqual(typed_ir["readonly_globals"][0]["array_len"], 256)
            self.assertEqual(
                typed_ir["runtime_preconditions"][0]["code"],
                "shift_count_in_range",
            )
            self.assertEqual(typed_ir["scalar_admission"]["status"], "covered")
            self.assertEqual(typed_ir["scalar_admission"]["precondition_count"], 1)
            self.assertEqual(
                typed_ir["scalar_admission"]["covered"][0]["code"],
                "shift_count_in_range",
            )
            self.assertIn(
                "fixture_contract.scalar_input_domain",
                typed_ir["scalar_admission"]["covered"][0]["covered_by"],
            )
            self.assertTrue(typed_ir["rust_draft_generated"])
            self.assertFalse(typed_ir["semantic_pass"])
            self.assertEqual(profile["candidate_generation"]["typed_ir"]["candidate_route"]["route"], "GenericTypedIr")
            self.assertEqual(
                profile["candidate_generation"]["typed_ir"]["runtime_preconditions"],
                typed_ir["runtime_preconditions"],
            )
            self.assertEqual(
                profile["candidate_generation"]["typed_ir"]["scalar_admission"],
                typed_ir["scalar_admission"],
            )
            self.assertFalse(profile["generated_draft_semantic_pass"])

    def test_generated_zero_token_scalar_typed_ir_candidate_routes_l0(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "typed-ir-route-signal",
            "source_commit": "1234567",
            "function_name": "add_one",
            "c_source": "int add_one(int value) { return value + 1; }",
            "fixture_hash": "fixture",
            "build_profile": {"compiler_command_source": "unit-test"},
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-typed-ir-route-signal"
            (evidence_dir / f"{prefix}-type-map.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-cfg.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-pointer-graph.json").write_text(
                json.dumps({"status": "not_applicable", "pointer_nodes": []}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-auto-translation-plan.json").write_text(
                json.dumps({"status": "draft_generated"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-test-translation-generated.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-clang-lowering-report.json").write_text(
                json.dumps(
                    {
                        "status": "lowered",
                        "typed_ir_candidate": {
                            "status": "generated",
                            "candidate_route": {
                                "route_id": "generic-typed-ir",
                                "route": "GenericTypedIr",
                                "candidate_generator": "GenericTypedIrEmitter",
                                "token_cost": 0,
                                "deprecated": False,
                            },
                            "readonly_globals": [],
                            "rust_draft_generated": True,
                            "semantic_pass": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            route = module.emit_route_decision(
                spec,
                evidence_dir,
                {"status": "generated"},
                {"status": "generated", "correctness_role": "candidate_context_only"},
            )
            profile = module.emit_validation_profile(
                spec,
                evidence_dir,
                route,
                {"status": "DRAFT_GENERATED"},
                {"status": "passed"},
            )

            self.assertEqual(route["level"], "L0")
            self.assertEqual(route["verification_profile"], "L0-dev")
            self.assertEqual(profile["route_level"], "L0")
            self.assertNotIn("unsafe_ledger", profile["required_gates"])
            self.assertNotIn("rust_tests", profile["required_gates"])
            self.assertIn(
                {
                    "feature": "typed_ir_zero_token_deterministic",
                    "route": "GenericTypedIr",
                    "token_cost": 0,
                    "weight": "deterministic_typed_ir",
                },
                route["rationale"],
            )
            self.assertFalse(route["candidate_generation"]["typed_ir"]["semantic_pass"])
            self.assertFalse(profile["generated_draft_semantic_pass"])

    def test_unresolved_scalar_admission_prevents_zero_token_l0_route(self) -> None:
        module = load_auto_migrate_module()
        candidate_generation = {
            "typed_ir": {
                "status": "generated",
                "candidate_route": {
                    "route": "GenericTypedIr",
                    "token_cost": 0,
                },
                "rust_draft_generated": True,
                "scalar_admission": {
                    "status": "unresolved",
                    "precondition_count": 1,
                    "covered": [],
                    "unresolved": [
                        {
                            "code": "signed_add_no_overflow",
                            "status": "unresolved",
                            "missing": ["c_boundary.scalar_arithmetic_contract.signed_overflow"],
                        }
                    ],
                },
            }
        }

        level, rationale = module.route_level(
            {"slice_id": "scalar-admission-route"},
            {"status": "generated"},
            {"status": "recorded"},
            {"status": "recorded"},
            {"pointer_nodes": []},
            {"status": "draft_generated"},
            candidate_generation,
        )

        self.assertEqual(level, "L1")
        self.assertEqual(rationale[0]["feature"], "typed_ir_scalar_admission_unresolved")
        self.assertEqual(rationale[0]["unresolved_count"], 1)

    def test_uncovered_scalar_runtime_preconditions_from_clang_report_stay_l1(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "uncovered-scalar-admission",
            "source_commit": "1234567",
            "function_name": "add_one",
            "c_source": "int add_one(int value) { return value + 1; }",
            "fixture_hash": "fixture",
            "build_profile": {"compiler_command_source": "unit-test"},
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-uncovered-scalar-admission"
            (evidence_dir / f"{prefix}-type-map.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-cfg.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-pointer-graph.json").write_text(
                json.dumps({"status": "not_applicable", "pointer_nodes": []}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-auto-translation-plan.json").write_text(
                json.dumps({"status": "draft_generated"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-test-translation-generated.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-clang-lowering-report.json").write_text(
                json.dumps(
                    {
                        "status": "lowered",
                        "typed_ir_candidate": {
                            "status": "generated",
                            "candidate_route": {
                                "route_id": "generic-typed-ir",
                                "route": "GenericTypedIr",
                                "candidate_generator": "GenericTypedIrEmitter",
                                "token_cost": 0,
                                "deprecated": False,
                            },
                            "readonly_globals": [],
                            "runtime_preconditions": [
                                {
                                    "code": "signed_add_no_overflow",
                                    "detail": "signed addition must not overflow",
                                    "ir_node": "IrExpr::Binary.Add",
                                    "source_span": None,
                                }
                            ],
                            "rust_draft_generated": True,
                            "semantic_pass": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            route = module.emit_route_decision(
                spec,
                evidence_dir,
                {"status": "generated"},
                {"status": "generated", "correctness_role": "candidate_context_only"},
            )
            profile = module.emit_validation_profile(
                spec,
                evidence_dir,
                route,
                {"status": "DRAFT_GENERATED"},
                {"status": "passed"},
            )

            typed_ir = route["candidate_generation"]["typed_ir"]
            self.assertEqual(route["level"], "L1")
            self.assertEqual(route["verification_profile"], "L1-dev")
            self.assertEqual(profile["route_level"], "L1")
            self.assertEqual(typed_ir["scalar_admission"]["status"], "unresolved")
            self.assertEqual(
                typed_ir["scalar_admission"]["unresolved"][0]["missing"],
                [
                    "c_boundary.scalar_arithmetic_contract.signed_overflow",
                    "fixture_contract.scalar_input_domain",
                ],
            )
            self.assertEqual(route["rationale"][0]["feature"], "typed_ir_scalar_admission_unresolved")
            self.assertEqual(route["rationale"][0]["unresolved_count"], 1)

    def test_scalar_admission_requires_matching_contract_and_input_domain(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "c_boundary": {
                "scalar_arithmetic_contract": {
                    "signed_overflow": "runtime_precondition_no_overflow",
                    "division_by_zero": "runtime_precondition_nonzero_divisor",
                    "signed_division_overflow": "runtime_precondition_excludes_min_div_minus_one",
                    "shift_count": "runtime_precondition_in_range",
                    "signed_right_shift": "explicit_implementation_defined_contract",
                }
            },
            "fixture_contract": {
                "scalar_input_domain": {
                    "case_source": "unit-test",
                    "parameters": [{"name": "value", "type": "int", "range": [-100, 100]}],
                    "covers_overflow_boundaries": False,
                }
            },
        }
        preconditions = [
            {"code": "signed_add_no_overflow"},
            {"code": "signed_sub_no_overflow"},
            {"code": "signed_mul_no_overflow"},
            {"code": "division_divisor_nonzero"},
            {"code": "modulo_divisor_nonzero"},
            {"code": "signed_division_no_overflow"},
            {"code": "signed_modulo_no_overflow"},
            {"code": "shift_count_in_range"},
            {"code": "signed_right_shift_implementation_defined"},
        ]

        covered = module.scalar_admission_from_runtime_preconditions(spec, preconditions)
        self.assertEqual(covered["status"], "covered")
        self.assertEqual(len(covered["covered"]), len(preconditions))
        self.assertEqual(covered["unresolved"], [])

        no_input_domain = json.loads(json.dumps(spec))
        no_input_domain["fixture_contract"]["scalar_input_domain"]["parameters"] = []
        missing_domain = module.scalar_admission_from_runtime_preconditions(
            no_input_domain,
            [{"code": "shift_count_in_range"}],
        )
        self.assertEqual(missing_domain["status"], "unresolved")
        self.assertEqual(missing_domain["unresolved"][0]["missing"], ["fixture_contract.scalar_input_domain"])

        wrong_contract = json.loads(json.dumps(spec))
        wrong_contract["c_boundary"]["scalar_arithmetic_contract"]["shift_count"] = "not_declared"
        wrong_shift = module.scalar_admission_from_runtime_preconditions(
            wrong_contract,
            [{"code": "shift_count_in_range"}],
        )
        self.assertEqual(wrong_shift["status"], "unresolved")
        self.assertEqual(
            wrong_shift["unresolved"][0]["missing"],
            ["c_boundary.scalar_arithmetic_contract.shift_count"],
        )

        wrong_signed_shift = json.loads(json.dumps(spec))
        wrong_signed_shift["c_boundary"]["scalar_arithmetic_contract"][
            "signed_right_shift"
        ] = "fail_closed_without_explicit_contract"
        signed_shift = module.scalar_admission_from_runtime_preconditions(
            wrong_signed_shift,
            [{"code": "signed_right_shift_implementation_defined"}],
        )
        self.assertEqual(signed_shift["status"], "unresolved")
        self.assertEqual(
            signed_shift["unresolved"][0]["missing"],
            ["c_boundary.scalar_arithmetic_contract.signed_right_shift"],
        )

        mixed = module.scalar_admission_from_runtime_preconditions(
            spec,
            [{"code": "signed_add_no_overflow"}, {"code": "unknown_scalar_precondition"}],
        )
        self.assertEqual(mixed["status"], "unresolved")
        self.assertEqual(mixed["covered"][0]["code"], "signed_add_no_overflow")
        self.assertEqual(
            mixed["unresolved"][0]["missing"],
            ["c_boundary.scalar_arithmetic_contract.unknown"],
        )

    def test_route_decision_records_primary_candidate_fallback_source(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "legacy-fallback-route-source",
            "source_commit": "1234567",
            "function_name": "identity",
            "c_source": "int identity(int value) { return value; }",
            "fixture_hash": "fixture",
            "build_profile": {"compiler_command_source": "unit-test"},
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-legacy-fallback-route-source"
            (evidence_dir / f"{prefix}-type-map.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-cfg.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-pointer-graph.json").write_text(
                json.dumps({"status": "not_applicable", "pointer_nodes": []}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-auto-translation-plan.json").write_text(
                json.dumps(
                    {
                        "status": "draft_generated",
                        "translation_source": {
                            "selected": "legacy-string-translator",
                            "fallback_from": "clang-lowered-typed-ir",
                            "fallback_reason": "clang_lowered_typed_ir_unavailable",
                        },
                    }
                ),
                encoding="utf-8",
            )
            (evidence_dir / f"{prefix}-test-translation-generated.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )

            route = module.emit_route_decision(
                spec,
                evidence_dir,
                {"status": "generated"},
                {"status": "generated", "correctness_role": "candidate_context_only"},
            )

            generation = route["candidate_generation"]
            self.assertEqual(generation["primary_candidate"]["selected"], "unknown")
            self.assertEqual(generation["primary_candidate"]["candidate_id"], "primary:unknown")
            self.assertEqual(generation["selected_candidate_id"], None)
            self.assertEqual(len(generation["compatibility_sources"]), 1)
            compatibility = generation["compatibility_sources"][0]
            self.assertEqual(compatibility["selected"], "legacy-string-translator")
            self.assertEqual(compatibility["candidate_id"], "compat:legacy-string-translator")
            self.assertEqual(compatibility["fallback_from"], "clang-lowered-typed-ir")
            self.assertEqual(compatibility["fallback_reason"], "clang_lowered_typed_ir_unavailable")

    def test_route_decision_records_candidate_set_and_selected_candidate(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "candidate-set-route-source",
            "source_commit": "1234567",
            "function_name": "identity",
            "c_source": "int identity(int value) { return value; }",
            "fixture_hash": "fixture",
            "build_profile": {"compiler_command_source": "unit-test"},
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-candidate-set-route-source"
            (evidence_dir / f"{prefix}-type-map.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-cfg.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-pointer-graph.json").write_text(
                json.dumps({"status": "not_applicable", "pointer_nodes": []}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-auto-translation-plan.json").write_text(
                json.dumps(
                    {
                        "status": "draft_generated",
                        "translation_source": {
                            "selected": "legacy-string-translator",
                            "fallback_from": "clang-lowered-typed-ir",
                            "fallback_reason": "clang_lowered_typed_ir_unavailable",
                        },
                    }
                ),
                encoding="utf-8",
            )
            (evidence_dir / f"{prefix}-test-translation-generated.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            baseline_manifest = {
                "schema_version": 1,
                "status": "skipped",
                "reason": "blocked_by_missing_tools",
                "correctness_role": "candidate_context_only",
                "output": None,
            }
            (evidence_dir / f"{prefix}-c2rust-baseline-manifest.json").write_text(
                json.dumps(baseline_manifest), encoding="utf-8"
            )

            route = module.emit_route_decision(
                spec,
                evidence_dir,
                {"status": "generated"},
                {
                    "status": "skipped",
                    "reason": "blocked_by_missing_tools",
                    "correctness_role": "candidate_context_only",
                },
            )

            generation = route["candidate_generation"]
            self.assertFalse(generation["generated_draft_semantic_pass"])
            self.assertEqual(
                generation["selection_policy"]["stage"],
                "p0_route_governance",
            )
            self.assertFalse(generation["selection_policy"]["semantic_acceptance"])
            self.assertEqual(
                generation["selected_candidate_id"],
                None,
            )
            self.assertEqual(generation["primary_candidate"]["selected"], "unknown")
            self.assertEqual(generation["primary_candidate"]["candidate_id"], "primary:unknown")
            self.assertEqual(
                generation["compatibility_sources"],
                [
                    {
                        "candidate_id": "compat:legacy-string-translator",
                        "selected": "legacy-string-translator",
                        "fallback": True,
                        "semantic_pass": False,
                        "compatibility_only": True,
                        "correctness_role": "compatibility_only",
                        "fallback_from": "clang-lowered-typed-ir",
                        "fallback_reason": "clang_lowered_typed_ir_unavailable",
                    }
                ],
            )
            candidates = {item["candidate_id"]: item for item in generation["candidate_set"]}
            self.assertEqual(
                set(candidates),
                {
                    "compat:legacy-string-translator",
                    "typed-ir:clang-lowered",
                    "c2rust-baseline",
                },
            )
            self.assertEqual(candidates["compat:legacy-string-translator"]["kind"], "legacy-string-translator")
            self.assertEqual(candidates["compat:legacy-string-translator"]["role"], "compatibility_rust_draft")
            self.assertEqual(candidates["compat:legacy-string-translator"]["correctness_role"], "compatibility_only")
            self.assertEqual(candidates["compat:legacy-string-translator"]["fallback_from"], "clang-lowered-typed-ir")
            self.assertEqual(candidates["typed-ir:clang-lowered"]["status"], "missing")
            self.assertFalse(candidates["typed-ir:clang-lowered"]["semantic_pass"])
            self.assertEqual(candidates["c2rust-baseline"]["status"], "skipped")
            self.assertEqual(candidates["c2rust-baseline"]["correctness_role"], "candidate_context_only")
            self.assertEqual(
                Path(candidates["c2rust-baseline"]["baseline_manifest"]["path"]).name,
                f"{prefix}-c2rust-baseline-manifest.json",
            )
            self.assertEqual(candidates["c2rust-baseline"]["baseline_manifest"]["status"], "skipped")
            self.assertIn("sha256", candidates["c2rust-baseline"]["baseline_manifest"])
            self.assertIsNone(candidates["c2rust-baseline"]["output_ref"])
            self.assertFalse(candidates["c2rust-baseline"]["semantic_pass"])
            self.assertEqual(generation["c2rust_baseline"], candidates["c2rust-baseline"])

    def test_route_decision_records_p0_route_governance_summary(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "p0-route-governance",
            "source_commit": "1234567",
            "function_name": "identity",
            "c_source": "int identity(int value) { return value; }",
            "fixture_hash": "fixture",
            "build_profile": {"compiler_command_source": "unit-test"},
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-p0-route-governance"
            (evidence_dir / f"{prefix}-type-map.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-cfg.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-pointer-graph.json").write_text(
                json.dumps({"status": "not_applicable", "pointer_nodes": []}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-auto-translation-plan.json").write_text(
                json.dumps(
                    {
                        "status": "draft_generated",
                        "translation_source": {"selected": "clang-lowered-typed-ir"},
                    }
                ),
                encoding="utf-8",
            )
            (evidence_dir / f"{prefix}-test-translation-generated.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            baseline_manifest = {
                "schema_version": 1,
                "status": "skipped",
                "reason": "blocked_by_missing_tools",
                "correctness_role": "candidate_context_only",
                "output": None,
            }
            (evidence_dir / f"{prefix}-c2rust-baseline-manifest.json").write_text(
                json.dumps(baseline_manifest), encoding="utf-8"
            )

            route = module.emit_route_decision(
                spec,
                evidence_dir,
                {"status": "generated"},
                {
                    "status": "skipped",
                    "reason": "blocked_by_missing_tools",
                    "correctness_role": "candidate_context_only",
                },
            )

            generation = route["candidate_generation"]
            self.assertEqual(generation["selection_policy"]["stage"], "p0_route_governance")
            summary = generation["governance_summary"]
            self.assertEqual(summary["stage"], "p0_route_governance")
            self.assertFalse(summary["semantic_acceptance"])
            self.assertFalse(summary["full_router"])
            self.assertEqual(summary["route_level"], route["level"])
            self.assertEqual(summary["route_status"], route["status"])
            self.assertIn("c_oracle", summary["validation_gate_summary"]["required_acceptance_gates"])
            self.assertIn("final_verification", summary["validation_gate_summary"]["required_acceptance_gates"])
            hard_gates = {gate["gate_id"]: gate for gate in summary["hard_gates"]}
            self.assertEqual(hard_gates["generated_candidate_semantic_acceptance"]["status"], "deferred")
            self.assertEqual(hard_gates["c2rust_baseline_semantic_source"]["status"], "forbidden")
            self.assertEqual(summary["fallback_summary"]["legacy_string_translator"]["status"], "not_used")

    def test_normalized_artifacts_preserve_translation_fallback_source(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "normalized-fallback-source",
            "source_commit": "1234567",
            "function_name": "identity",
            "c_source": "int identity(int value) { return value; }",
            "fixture_hash": "fixture",
            "build_profile": {"compiler_command_source": "unit-test"},
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            evidence_dir = tmp_path / "evidence"
            evidence_dir.mkdir()
            slice_spec_path = tmp_path / "slice.json"
            slice_spec_path.write_text(json.dumps(spec), encoding="utf-8")
            prefix = "l3-normalized-fallback-source"
            (evidence_dir / f"{prefix}-translator-input.json").write_text(
                json.dumps({"slice_id": "normalized-fallback-source"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-type-map.json").write_text(
                json.dumps({"type_map": {"mappings": [], "uncertainties": []}}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-cfg.json").write_text(
                json.dumps({"cfg": {"functions": []}}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-pointer-graph.json").write_text(
                json.dumps({"pointer_graph": {"nodes": [], "edges": []}}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-auto-translation-plan.json").write_text(
                json.dumps(
                    {
                        "status": "generated",
                        "translation_source": {
                            "selected": "legacy-string-translator",
                            "fallback_from": "clang-lowered-typed-ir",
                            "fallback_reason": "clang_lowered_typed_ir_unavailable",
                        },
                        "plan": {
                            "translation_rule_ids": ["primitive-return"],
                            "unsupported_node_count": 0,
                            "unsafe_candidate_count": 0,
                            "call_expressions": [],
                        },
                        "errors": [],
                    }
                ),
                encoding="utf-8",
            )
            (evidence_dir / f"{prefix}-rust-draft.rs").write_text(
                "pub fn identity(value: i32) -> i32 { value }\n", encoding="utf-8"
            )

            module.normalize_translation_artifacts(spec, slice_spec_path, evidence_dir)

            plan = json.loads((evidence_dir / f"{prefix}-auto-translation-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["translation_source"]["selected"], "legacy-string-translator")
            self.assertEqual(plan["translation_source"]["fallback_from"], "clang-lowered-typed-ir")
            events = [
                json.loads(line)
                for line in (evidence_dir / f"{prefix}-auto-translation-events.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            fallback_events = [
                event for event in events if event.get("event_kind") == "translation_fallback"
            ]
            self.assertEqual(len(fallback_events), 1)
            self.assertEqual(fallback_events[0]["selected"], "legacy-string-translator")
            self.assertEqual(fallback_events[0]["fallback_from"], "clang-lowered-typed-ir")

    def test_scalar_typed_ir_candidate_without_zero_token_cost_stays_l1(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "typed-ir-missing-token-cost",
            "source_commit": "1234567",
            "function_name": "add_one",
            "c_source": "int add_one(int value) { return value + 1; }",
            "fixture_hash": "fixture",
            "build_profile": {"compiler_command_source": "unit-test"},
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-typed-ir-missing-token-cost"
            (evidence_dir / f"{prefix}-type-map.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-cfg.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-pointer-graph.json").write_text(
                json.dumps({"status": "not_applicable", "pointer_nodes": []}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-auto-translation-plan.json").write_text(
                json.dumps({"status": "draft_generated"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-test-translation-generated.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-clang-lowering-report.json").write_text(
                json.dumps(
                    {
                        "status": "lowered",
                        "typed_ir_candidate": {
                            "status": "generated",
                            "candidate_route": {
                                "route_id": "generic-typed-ir",
                                "route": "GenericTypedIr",
                                "candidate_generator": "GenericTypedIrEmitter",
                                "deprecated": False,
                            },
                            "readonly_globals": [],
                            "rust_draft_generated": True,
                            "semantic_pass": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            route = module.emit_route_decision(
                spec,
                evidence_dir,
                {"status": "generated"},
                {"status": "generated", "correctness_role": "candidate_context_only"},
            )

            self.assertEqual(route["level"], "L1")
            self.assertNotIn(
                {
                    "feature": "typed_ir_zero_token_deterministic",
                    "route": "GenericTypedIr",
                    "token_cost": 0,
                    "weight": "deterministic_typed_ir",
                },
                route["rationale"],
            )
            self.assertIn(
                {
                    "feature": "typed_ir_candidate_generated",
                    "route": "GenericTypedIr",
                    "weight": "generic_typed_ir",
                },
                route["rationale"],
            )

    def test_scalar_typed_ir_candidate_with_nonzero_token_cost_stays_l1(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "typed-ir-nonzero-token-cost",
            "source_commit": "1234567",
            "function_name": "add_one",
            "c_source": "int add_one(int value) { return value + 1; }",
            "fixture_hash": "fixture",
            "build_profile": {"compiler_command_source": "unit-test"},
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-typed-ir-nonzero-token-cost"
            (evidence_dir / f"{prefix}-type-map.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-cfg.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-pointer-graph.json").write_text(
                json.dumps({"status": "not_applicable", "pointer_nodes": []}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-auto-translation-plan.json").write_text(
                json.dumps({"status": "draft_generated"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-test-translation-generated.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-clang-lowering-report.json").write_text(
                json.dumps(
                    {
                        "status": "lowered",
                        "typed_ir_candidate": {
                            "status": "generated",
                            "candidate_route": {
                                "route_id": "generic-typed-ir",
                                "route": "GenericTypedIr",
                                "candidate_generator": "GenericTypedIrEmitter",
                                "token_cost": 1,
                                "deprecated": False,
                            },
                            "readonly_globals": [],
                            "rust_draft_generated": True,
                            "semantic_pass": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            route = module.emit_route_decision(
                spec,
                evidence_dir,
                {"status": "generated"},
                {"status": "generated", "correctness_role": "candidate_context_only"},
            )

            self.assertEqual(route["level"], "L1")
            self.assertNotIn(
                {
                    "feature": "typed_ir_zero_token_deterministic",
                    "route": "GenericTypedIr",
                    "token_cost": 0,
                    "weight": "deterministic_typed_ir",
                },
                route["rationale"],
            )
            self.assertIn(
                {
                    "feature": "typed_ir_candidate_generated",
                    "route": "GenericTypedIr",
                    "weight": "generic_typed_ir",
                },
                route["rationale"],
            )

    def test_generated_typed_ir_candidate_with_unknown_pointer_role_routes_l2_not_l0(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "typed-ir-unknown-pointer-role",
            "source_commit": "1234567",
            "function_name": "first_i32",
            "c_source": "int first_i32(const int* values) { return values[0]; }",
            "fixture_hash": "fixture",
            "build_profile": {"compiler_command_source": "unit-test"},
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-typed-ir-unknown-pointer-role"
            (evidence_dir / f"{prefix}-type-map.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-cfg.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-pointer-graph.json").write_text(
                json.dumps(
                    {
                        "status": "recorded",
                        "pointer_nodes": [
                            {"name": "values", "ownership_role": "unknown"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (evidence_dir / f"{prefix}-auto-translation-plan.json").write_text(
                json.dumps({"status": "draft_generated"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-test-translation-generated.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-clang-lowering-report.json").write_text(
                json.dumps(
                    {
                        "status": "lowered",
                        "typed_ir_candidate": {
                            "status": "generated",
                            "candidate_route": {
                                "route_id": "generic-typed-ir",
                                "route": "GenericTypedIr",
                                "candidate_generator": "GenericTypedIrEmitter",
                                "token_cost": 0,
                                "deprecated": False,
                            },
                            "readonly_globals": [],
                            "rust_draft_generated": True,
                            "semantic_pass": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            route = module.emit_route_decision(
                spec,
                evidence_dir,
                {"status": "generated"},
                {"status": "generated", "correctness_role": "candidate_context_only"},
            )

            self.assertEqual(route["level"], "L2")
            self.assertEqual(route["verification_profile"], "L2-dev")
            self.assertIn({"feature": "unknown_pointer_role", "weight": "medium"}, route["rationale"])
            self.assertNotIn(
                {
                    "feature": "typed_ir_zero_token_deterministic",
                    "route": "GenericTypedIr",
                    "token_cost": 0,
                    "weight": "deterministic_typed_ir",
                },
                route["rationale"],
            )
            self.assertIn(
                {
                    "feature": "typed_ir_candidate_generated",
                    "route": "GenericTypedIr",
                    "weight": "generic_typed_ir",
                },
                route["rationale"],
            )

    def test_generated_typed_ir_candidate_with_alias_risk_routes_l2_not_l1(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "typed-ir-alias-risk-floor",
            "source_commit": "1234567",
            "function_name": "copy_i32",
            "c_source": "int copy_i32(const int* values, int* out) { *out = values[0]; return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {"compiler_command_source": "unit-test"},
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-typed-ir-alias-risk-floor"
            (evidence_dir / f"{prefix}-type-map.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-cfg.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-pointer-graph.json").write_text(
                json.dumps(
                    {
                        "status": "recorded",
                        "pointer_nodes": [
                            {"name": "values", "ownership_role": "input"},
                            {"name": "out", "ownership_role": "output"},
                        ],
                        "alias_contract": {
                            "decision": "requires_noalias_contract",
                            "proven": False,
                            "requires_noalias": True,
                        },
                        "alias_risks": [
                            {
                                "pointer_nodes": ["values", "out"],
                                "risk_level": "unknown_alias",
                                "gate_decision": "requires_noalias_contract",
                                "requires_noalias": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (evidence_dir / f"{prefix}-auto-translation-plan.json").write_text(
                json.dumps({"status": "draft_generated"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-test-translation-generated.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-clang-lowering-report.json").write_text(
                json.dumps(
                    {
                        "status": "lowered",
                        "typed_ir_candidate": {
                            "status": "generated",
                            "candidate_route": {
                                "route_id": "generic-typed-ir",
                                "route": "GenericTypedIr",
                                "candidate_generator": "GenericTypedIrEmitter",
                                "token_cost": 0,
                                "deprecated": False,
                            },
                            "readonly_globals": [],
                            "rust_draft_generated": True,
                            "semantic_pass": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            route = module.emit_route_decision(
                spec,
                evidence_dir,
                {"status": "generated"},
                {"status": "generated", "correctness_role": "candidate_context_only"},
            )

            self.assertEqual(route["level"], "L2")
            self.assertEqual(route["verification_profile"], "L2-dev")
            self.assertEqual(
                route["candidate_generation"]["typed_ir"]["candidate_route"]["route"],
                "GenericTypedIr",
            )
            self.assertIn(
                {
                    "feature": "alias_requires_noalias_contract",
                    "risk_count": 1,
                    "weight": "medium",
                },
                route["rationale"],
            )
            self.assertIn(
                {
                    "feature": "typed_ir_candidate_generated",
                    "route": "GenericTypedIr",
                    "weight": "generic_typed_ir",
                },
                route["rationale"],
            )

    def test_generated_typed_ir_candidate_does_not_override_blocked_alias_route(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "typed-ir-blocked-alias-floor",
            "source_commit": "1234567",
            "function_name": "copy_i32",
            "c_source": "int copy_i32(const int* values, int* out) { *out = values[0]; return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {"compiler_command_source": "unit-test"},
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-typed-ir-blocked-alias-floor"
            (evidence_dir / f"{prefix}-type-map.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-cfg.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-pointer-graph.json").write_text(
                json.dumps(
                    {
                        "status": "recorded",
                        "pointer_nodes": [
                            {"name": "values", "ownership_role": "input"},
                            {"name": "out", "ownership_role": "output"},
                        ],
                        "alias_contract": {
                            "decision": "blocked",
                            "proven": False,
                            "requires_noalias": True,
                        },
                        "alias_risks": [
                            {
                                "pointer_nodes": ["values", "out"],
                                "risk_level": "unknown_alias",
                                "gate_decision": "blocked",
                                "requires_noalias": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (evidence_dir / f"{prefix}-auto-translation-plan.json").write_text(
                json.dumps({"status": "draft_generated"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-test-translation-generated.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-clang-lowering-report.json").write_text(
                json.dumps(
                    {
                        "status": "lowered",
                        "typed_ir_candidate": {
                            "status": "generated",
                            "candidate_route": {
                                "route_id": "generic-typed-ir",
                                "route": "GenericTypedIr",
                                "candidate_generator": "GenericTypedIrEmitter",
                                "token_cost": 0,
                                "deprecated": False,
                            },
                            "readonly_globals": [],
                            "rust_draft_generated": True,
                            "semantic_pass": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            route = module.emit_route_decision(
                spec,
                evidence_dir,
                {"status": "generated"},
                {"status": "generated", "correctness_role": "candidate_context_only"},
            )

            self.assertEqual(route["level"], "L3")
            self.assertEqual(route["verification_profile"], "L3-dev")
            self.assertEqual(
                route["candidate_generation"]["typed_ir"]["candidate_route"]["route"],
                "GenericTypedIr",
            )
            self.assertIn({"feature": "alias_blocked", "weight": "high"}, route["rationale"])
            self.assertIn(
                {
                    "feature": "typed_ir_candidate_generated",
                    "route": "GenericTypedIr",
                    "weight": "generic_typed_ir",
                },
                route["rationale"],
            )

    def test_unsupported_typed_ir_candidate_preserves_reason_and_routes_l2(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "typed-ir-unsupported-route",
            "source_commit": "1234567",
            "function_name": "call_fn",
            "c_source": "int call_fn(int value) { return helper(value); }",
            "fixture_hash": "fixture",
            "build_profile": {"compiler_command_source": "unit-test"},
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-typed-ir-unsupported-route"
            (evidence_dir / f"{prefix}-type-map.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-cfg.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-pointer-graph.json").write_text(
                json.dumps({"status": "not_applicable", "pointer_nodes": []}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-auto-translation-plan.json").write_text(
                json.dumps({"status": "draft_generated"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-test-translation-generated.json").write_text(
                json.dumps({"status": "recorded"}), encoding="utf-8"
            )
            (evidence_dir / f"{prefix}-clang-lowering-report.json").write_text(
                json.dumps(
                    {
                        "status": "lowered",
                        "typed_ir_candidate": {
                            "status": "unsupported",
                            "candidate_route": {
                                "route_id": "unsupported",
                                "route": "Unsupported",
                                "candidate_generator": "GenericTypedIrEmitter",
                                "token_cost": 0,
                                "deprecated": False,
                            },
                            "readonly_globals": [],
                            "rust_draft_generated": False,
                            "semantic_pass": False,
                            "unsupported_reason": "call expressions are not supported by typed IR emitter",
                        },
                    }
                ),
                encoding="utf-8",
            )

            route = module.emit_route_decision(
                spec,
                evidence_dir,
                {"status": "generated"},
                {"status": "generated", "correctness_role": "candidate_context_only"},
            )
            profile = module.emit_validation_profile(
                spec,
                evidence_dir,
                route,
                {"status": "DRAFT_GENERATED"},
                {"status": "passed"},
            )

            self.assertEqual(route["level"], "L2")
            self.assertEqual(route["verification_profile"], "L2-dev")
            typed_ir = route["candidate_generation"]["typed_ir"]
            self.assertEqual(typed_ir["status"], "unsupported")
            self.assertEqual(
                typed_ir["unsupported_reason"],
                "call expressions are not supported by typed IR emitter",
            )
            self.assertIn(
                {
                    "feature": "typed_ir_candidate_unsupported",
                    "reason": "call expressions are not supported by typed IR emitter",
                    "weight": "repair_queue",
                },
                route["rationale"],
            )
            self.assertEqual(
                profile["candidate_generation"]["typed_ir"]["unsupported_reason"],
                "call expressions are not supported by typed IR emitter",
            )
            self.assertFalse(profile["generated_draft_semantic_pass"])

    def test_semantic_pass_requires_validation_profile_passed(self) -> None:
        auto_migrate = load_auto_migrate_module()

        accepted = {"status": "accepted"}
        rust_check = {"status": "passed"}
        profile = {"status": "incomplete", "skipped_gates": [{"gate": "c_oracle_diff", "reason": "SKIPPED"}]}
        sufficient_contract = {"status": "sufficient_for_semantic_pass"}

        self.assertFalse(auto_migrate.semantic_pass_for_run(accepted, rust_check, profile))
        self.assertFalse(auto_migrate.semantic_pass_for_run(None, rust_check, {"status": "passed"}))
        self.assertFalse(auto_migrate.semantic_pass_for_run(accepted, rust_check, {"status": "passed", "skipped_gates": []}))
        self.assertTrue(
            auto_migrate.semantic_pass_for_run(
                accepted,
                rust_check,
                {
                    "status": "passed",
                    "skipped_gates": [],
                    "oracle_boundary_contract": sufficient_contract,
                },
            )
        )
        self.assertFalse(
            auto_migrate.semantic_pass_for_run(
                accepted,
                rust_check,
                {"status": "passed", "route_level": "L4", "skipped_gates": []},
            )
        )
        self.assertTrue(
            auto_migrate.semantic_pass_for_run(
                accepted,
                rust_check,
                {
                    "status": "passed",
                    "route_level": "L4",
                    "skipped_gates": [],
                    "accepted_evidence_authoritative": True,
                    "generated_draft_semantic_pass": False,
                    "oracle_boundary_contract": sufficient_contract,
                },
            )
        )

    def test_generates_candidate_without_claiming_semantic_pass(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            out_root = Path(tmp) / "evidence"
            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertFalse(manifest["claim_boundary"]["semantic_pass"])
            self.assertEqual(manifest["source_commit"], "d40f29fd42ed9158e3eb3e221dca50e4b627f7a8")
            self.assertEqual(manifest["fixture"]["hash"], "zlib-adler32-fixture")
            self.assertEqual(manifest["oracle"]["status"], "SKIPPED_LOCAL_NO_C_TOOLCHAIN")
            self.assertEqual(manifest["oracle"]["fixture"], "validation/l2_slices/fixtures/zlib-adler32-c-oracle.json")
            self.assertEqual(manifest["replay"]["fixture"], "validation/l2_slices/fixtures/zlib-adler32-c-oracle.json")
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertTrue(
                (out_root / "zlib-ng" / "auto-translation" / "adler32-step" / "l3-adler32-step-type-map.json").exists()
            )

    def test_compound_and_increment_translation_flows_through_auto_migrate(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "compound-inc-dec",
            "source_commit": "1234567",
            "function_name": "compound_inc_dec",
            "c_source": "int compound_inc_dec(int value) { value += 1; value++; --value; return value; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "compound-inc-dec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "compound-inc-dec"
            draft = (evidence_dir / "l3-compound-inc-dec-rust-draft.rs").read_text(encoding="utf-8")
            plan = json.loads(
                (evidence_dir / "l3-compound-inc-dec-auto-translation-plan.json").read_text(encoding="utf-8")
            )
            cfg = json.loads((evidence_dir / "l3-compound-inc-dec-cfg.json").read_text(encoding="utf-8"))
            statement_kinds = cfg["functions"][0]["basic_blocks"][0]["statement_kinds"]

            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertFalse(manifest["claim_boundary"]["semantic_pass"])
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertIn("value += 1;", draft)
            self.assertIn("value -= 1;", draft)
            self.assertIn("compound-assignment", plan["translation_summary"]["translation_rule_ids"])
            self.assertIn("increment-decrement", plan["translation_summary"]["translation_rule_ids"])
            self.assertIn("compound_assignment", statement_kinds)
            self.assertIn("inc_dec", statement_kinds)

    def test_call_expression_evidence_flows_through_auto_migrate(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": "1234567",
            "function_name": "call_expression",
            "c_source": "int call_expression(int value) { int first = call_expression(value); value = call_expression(first); return call_expression(value); }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "call-expression.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "call-expression"
            plan = json.loads(
                (evidence_dir / "l3-call-expression-auto-translation-plan.json").read_text(
                    encoding="utf-8"
                )
            )
            cfg = json.loads((evidence_dir / "l3-call-expression-cfg.json").read_text(encoding="utf-8"))
            context_pack = json.loads(
                (evidence_dir / "l3-call-expression-context-pack.json").read_text(encoding="utf-8")
            )

            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertIn("call_expression", cfg["functions"][0]["basic_blocks"][0]["statement_kinds"])
            self.assertIn("bounded-call-expression", plan["translation_summary"]["translation_rule_ids"])
            self.assertEqual(len(plan["translation_summary"]["call_expressions"]), 3)
            self.assertEqual(plan["translation_summary"]["call_expressions"][0]["callee"], "call_expression")
            self.assertEqual(
                context_pack["direct_call_edges"][0],
                {
                    "callee": "call_expression",
                    "arguments": ["value"],
                    "source_expression": "call_expression(value)",
                    "statement_context": "declaration_initializer",
                },
            )

    def test_global_dependency_flows_into_context_type_map_and_oracle_requirements(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "global-dependency",
            "source_commit": "1234567",
            "function_name": "global_dependency",
            "c_source": "int global_dependency(int value) { return value + 1; }",
            "fixture_hash": "fixture",
            "source": {
                "source_root": "unit",
                "source_commit": "1234567",
                "repo_commit": "1234567",
                "source_file_hashes": {"unit/global.c": "global-sha"},
            },
            "build_profile": {
                "include_paths": ["inc"],
                "defines": ["UNIT_TEST=1"],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "cases": [
                    {
                        "id": "case-one",
                        "input_ref": "cases[0]",
                        "expected_ref": "inline",
                        "expected_outputs": {"value": 42},
                    }
                ],
                "observable_outputs": ["value"],
                "behavior_fields": ["value"],
            },
            "c_boundary": {
                "files": [{"path": "unit/global.c", "role": "source", "sha256": "global-sha"}],
                "functions": ["global_dependency"],
                "signatures": [
                    {
                        "function": "global_dependency",
                        "return_type": "int",
                        "parameters": [{"name": "value", "c_type": "int"}],
                    }
                ],
                "direct_dependencies": [
                    {"kind": "type", "name": "int", "source": "extracted_signature"},
                    {
                        "kind": "global",
                        "name": "table",
                        "source": "extracted_function_body_reference",
                        "definition_status": "same_file_top_level_declared",
                        "source_span": {
                            "file": "unit/global.c",
                            "line_start": 3,
                            "line_end": 3,
                            "sha256": "table-sha",
                        },
                        "sha256": "table-sha",
                    },
                ],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "global-dependency.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            evidence_dir = out_root / "demo" / "auto-translation" / "global-dependency"
            context_pack = json.loads(
                (evidence_dir / "l3-global-dependency-context-pack.json").read_text(encoding="utf-8")
            )
            type_map = json.loads((evidence_dir / "l3-global-dependency-type-map.json").read_text(encoding="utf-8"))
            oracle_status = json.loads(
                (evidence_dir / "l3-global-dependency-c-oracle-status.json").read_text(encoding="utf-8")
            )
            cache = json.loads(
                (evidence_dir / "l3-global-dependency-auto-cache-metadata.json").read_text(encoding="utf-8")
            )
            harness_path = evidence_dir / "l3-global-dependency-c-oracle-harness-draft.c"
            harness = harness_path.read_text(encoding="utf-8")
            harness_sha256 = hashlib.sha256(harness_path.read_bytes()).hexdigest()

            self.assertEqual(context_pack["global_dependencies"][0]["name"], "table")
            self.assertEqual(context_pack["source_boundary"]["globals"], ["table"])
            self.assertEqual(type_map["global_dependencies"][0]["name"], "table")
            self.assertEqual(type_map["global_dependencies"][0]["source_span"]["file"], "unit/global.c")
            self.assertEqual(oracle_status["global_linkage_requirements"][0]["name"], "table")
            self.assertIn("global dependency: table", harness)
            self.assertIn("int global_dependency(int value);", harness)
            self.assertIn("fixture input: unit-test-fixture.json", harness)
            self.assertIn("fixture cases: 1", harness)
            self.assertIn("observable outputs: value", harness)
            self.assertIn(
                'fixture case: case-one input_ref=cases[0] expected_ref=inline expected_outputs={"value": 42}',
                harness,
            )
            self.assertIn("source file: unit/global.c (sha256: global-sha)", harness)
            self.assertEqual(
                oracle_status["harness_contract"]["function_prototype"],
                "int global_dependency(int value);",
            )
            self.assertEqual(
                oracle_status["harness_contract"]["fixture"]["path"],
                "unit-test-fixture.json",
            )
            self.assertEqual(oracle_status["toolchain_status"], "DRAFT_NOT_EXECUTED")
            self.assertIn("compile_execution", oracle_status)
            self.assertEqual(
                oracle_status["compile_execution"],
                {
                    "status": "skipped_by_flag",
                    "attempted": False,
                    "argv": oracle_status["compile_command_draft"]["argv"],
                    "working_directory": str(evidence_dir).replace("\\", "/"),
                    "toolchain_adapter": "not_executed",
                    "toolchain_status_after_attempt": "DRAFT_NOT_EXECUTED",
                    "semantic_pass": False,
                    "diagnostics": ["C oracle compile execution skipped by --skip-c-oracle."],
                },
            )
            self.assertEqual(
                oracle_status["fixture_binding"],
                {
                    "path": "unit-test-fixture.json",
                    "case_count": 1,
                    "binding_status": "declared_not_executed",
                    "behavior_fields": ["value"],
                    "observable_outputs": ["value"],
                    "case_bindings": [
                        {
                            "id": "case-one",
                            "input_ref": "cases[0]",
                            "expected_ref": "inline",
                            "expected_outputs": {"value": 42},
                            "observable_outputs": ["value"],
                            "missing_observable_outputs": [],
                            "binding_status": "declared_not_executed",
                        }
                    ],
                    "expected_output_status": "declared_not_executed",
                },
            )
            self.assertEqual(
                oracle_status["harness_contract"]["fixture"],
                oracle_status["fixture_binding"],
            )
            self.assertEqual(
                oracle_status["harness_contract"]["source_files"][0],
                {"path": "unit/global.c", "role": "source", "sha256": "global-sha"},
            )
            self.assertIn("compile_command_draft", oracle_status)
            self.assertEqual(
                oracle_status["compile_command_draft"],
                {
                    "working_directory": str(evidence_dir).replace("\\", "/"),
                    "source_root": "unit",
                    "defines": ["UNIT_TEST=1"],
                    "resolved_include_paths": ["unit/inc"],
                    "link_source_files": [
                        {
                            "path": "unit/global.c",
                            "resolved_path": "unit/global.c",
                            "role": "source",
                            "sha256": "global-sha",
                            "resolution": "source_root_relative",
                        }
                    ],
                    "link_strategy": "compile_harness_with_declared_c_boundary_sources",
                    "oracle_source_mode": "declared_c_boundary_sources",
                    "argv": [
                        "cc",
                        "-std=c99",
                        "-DUNIT_TEST=1",
                        "-Iunit/inc",
                        "l3-global-dependency-c-oracle-harness-draft.c",
                        "unit/global.c",
                        "-o",
                        "l3-global-dependency-c-oracle-harness-draft.exe",
                    ],
                    "status": "draft_not_executed",
                },
            )
            self.assertEqual(
                oracle_status["harness_draft_ref"],
                {
                    "path": harness_path.as_posix(),
                    "status": "draft",
                    "sha256": harness_sha256,
                },
            )
            self.assertEqual(cache["c_oracle_harness_identity"], oracle_status["harness_draft_ref"])
            self.assertIn("c_oracle_harness_identity", cache["cache_input_fields"])

    def test_declared_external_callee_context_allows_helper_rust_check(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "external-callee",
            "source_commit": "1234567",
            "function_name": "call_helper_chain",
            "c_source": (
                "int call_helper_chain(int value) { "
                "int first = helper_add_one(value); "
                "value = helper_add_one(first); "
                "return helper_add_one(value); "
                "}"
            ),
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "c_boundary": {
                "files": [
                    {"path": "unit/caller.c", "role": "slice_entry", "sha256": "caller-sha"},
                    {"path": "unit/helper.c", "role": "external_direct_callee", "sha256": "helper-sha"},
                ],
                "signatures": [
                    {
                        "id": "sig-call-helper-chain",
                        "function": "call_helper_chain",
                        "return_type": "int",
                        "parameters": [{"name": "value", "c_type": "int"}],
                        "c_source": (
                            "int call_helper_chain(int value) { "
                            "int first = helper_add_one(value); "
                            "value = helper_add_one(first); "
                            "return helper_add_one(value); "
                            "}"
                        ),
                    },
                    {
                        "id": "sig-helper-add-one",
                        "role": "external_direct_callee",
                        "function": "helper_add_one",
                        "return_type": "int",
                        "parameters": [{"name": "value", "c_type": "int"}],
                        "source_ref": "unit/helper.c#helper_add_one",
                        "signature_sha256": "helper-signature-sha",
                        "definition_status": "real_source_bound",
                        "c_source": "int helper_add_one(int value) { return value + 1; }",
                    },
                ],
                "direct_dependencies": [
                    {"kind": "callee", "name": "helper_add_one", "source": "unit/helper.c#helper_add_one"}
                ],
                "external_direct_callees": [
                    {
                        "name": "helper_add_one",
                        "signature_ref": "sig-helper-add-one",
                        "source_files": [{"path": "unit/helper.c", "sha256": "helper-sha"}],
                        "definition_status": "real_source_bound",
                        "stub_boundary": "compile_only",
                    }
                ],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "external-callee.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "external-callee"
            draft = (evidence_dir / "l3-external-callee-rust-draft.rs").read_text(encoding="utf-8")
            plan = json.loads(
                (evidence_dir / "l3-external-callee-auto-translation-plan.json").read_text(encoding="utf-8")
            )
            context_pack = json.loads(
                (evidence_dir / "l3-external-callee-context-pack.json").read_text(encoding="utf-8")
            )

            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertIn("fn helper_add_one(value: i32) -> i32", draft)
            self.assertIn("external callee context stub: helper_add_one", draft)
            external_callee = plan["translation_summary"]["external_direct_callees"][0]
            self.assertEqual(external_callee["name"], "helper_add_one")
            self.assertEqual(external_callee["signature_ref"], "sig-helper-add-one")
            self.assertEqual(external_callee["parameters"], [{"name": "value", "c_type": "int"}])
            self.assertEqual(external_callee["return_type"], "int")
            self.assertEqual(external_callee["stub_kind"], "compile_only")
            self.assertFalse(external_callee["semantics_verified"])
            call_expressions = plan["translation_summary"]["call_expressions"]
            self.assertEqual(len(call_expressions), 3)
            self.assertEqual(
                call_expressions[0]["callee_signature_id"],
                "sig-helper-add-one",
            )
            for call in call_expressions:
                self.assertEqual(call["callee"], "helper_add_one")
                self.assertEqual(call["callee_scope"], "external_direct_callee")
                self.assertEqual(call["callee_signature_id"], "sig-helper-add-one")
                self.assertEqual(call["callee_source_ref"], "unit/helper.c#helper_add_one")
                self.assertEqual(call["definition_status"], "real_source_bound")
                self.assertEqual(call["stub_status"], "compile_only")
            self.assertEqual(plan["inputs"]["external_callee_context"]["status"], "recorded")
            self.assertEqual(plan["inputs"]["external_callee_context"]["declared_count"], 1)
            self.assertEqual(plan["inputs"]["external_callee_context"]["blocked_count"], 0)
            context_callee = context_pack["external_direct_callees"][0]
            self.assertEqual(context_callee["name"], "helper_add_one")
            self.assertEqual(context_callee["parameters"], [{"name": "value", "c_type": "int"}])
            self.assertEqual(context_callee["return_type"], "int")
            self.assertEqual(context_callee["stub_kind"], "compile_only")
            self.assertFalse(context_callee["semantics_verified"])
            self.assertEqual(context_pack["direct_call_edges"], call_expressions)
            bindings = context_pack["call_edge_to_callee_binding"]
            self.assertEqual(len(bindings), 3)
            for binding, call in zip(bindings, call_expressions):
                self.assertEqual(binding["callee"], "helper_add_one")
                self.assertEqual(binding["signature_ref"], "sig-helper-add-one")
                self.assertEqual(binding["source_expression"], call["source_expression"])
                self.assertEqual(binding["statement_context"], call["statement_context"])
                self.assertEqual(binding["stub_kind"], "compile_only")
                self.assertFalse(binding["semantics_verified"])
            self.assertEqual(
                manifest["claim_boundary"]["external_callee_scope"]["status"],
                "compile_context_only",
            )
            self.assertFalse(manifest["claim_boundary"]["generated_draft_semantic_pass"])

    def test_undeclared_external_callee_context_blocks_silent_stub_injection(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "missing-external-callee",
            "source_commit": "1234567",
            "function_name": "call_missing_helper",
            "c_source": (
                "int call_missing_helper(int value) { "
                "int first = helper_add_one(value); "
                "return helper_add_one(first); "
                "}"
            ),
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "missing-external-callee.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "missing-external-callee"
            draft = (evidence_dir / "l3-missing-external-callee-rust-draft.rs").read_text(encoding="utf-8")
            plan = json.loads(
                (evidence_dir / "l3-missing-external-callee-auto-translation-plan.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(manifest["rust_check"]["status"], "failed")
            self.assertNotIn("fn helper_add_one", draft)
            self.assertEqual(
                manifest["rust_check"]["external_callee_context"]["status"],
                "blocked",
            )
            self.assertEqual(
                manifest["rust_check"]["external_callee_context"]["blocked_callees"][0]["name"],
                "helper_add_one",
            )
            self.assertEqual(plan["inputs"]["external_callee_context"]["status"], "blocked")
            self.assertEqual(plan["inputs"]["external_callee_context"]["declared_count"], 0)
            self.assertEqual(plan["inputs"]["external_callee_context"]["blocked_count"], 1)
            self.assertEqual(
                plan["translation_summary"]["external_direct_callee_blocks"][0]["reason"],
                "missing_declared_external_direct_callee",
            )

    def test_real_fdb_kv_set_records_fail_closed_callee_provenance_without_semantic_claim(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-kv-set.json"
        with tempfile.TemporaryDirectory(prefix="auto-migrate-real-fdb-kv-set-") as tmp:
            out_root = Path(tmp) / "evidence"

            result = subprocess.run(
                [
                    sys.executable,
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                    "--skip-rust-check",
                    "--emit-clang-dry-run",
                    "--emit-clang-lowering-report",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "flashdb" / "auto-translation" / "real-fdb-kv-set"
            translator_input = json.loads(
                (evidence_dir / "l3-real-fdb-kv-set-translator-input.json").read_text(encoding="utf-8")
            )
            plan = json.loads(
                (evidence_dir / "l3-real-fdb-kv-set-auto-translation-plan.json").read_text(encoding="utf-8")
            )
            context_pack = json.loads(
                (evidence_dir / "l3-real-fdb-kv-set-context-pack.json").read_text(encoding="utf-8")
            )
            route = json.loads(
                (evidence_dir / "l3-real-fdb-kv-set-route-decision.json").read_text(encoding="utf-8")
            )
            profile = json.loads(
                (evidence_dir / "l3-real-fdb-kv-set-validation-profile.json").read_text(encoding="utf-8")
            )
            blocked = json.loads(
                (evidence_dir / "l3-real-fdb-kv-set-self-healing-blocked-repairs.json").read_text(encoding="utf-8")
            )
            capability = json.loads(
                (evidence_dir / "l3-real-fdb-kv-set-capability-delta.json").read_text(encoding="utf-8")
            )
            validation_result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--target-id",
                    "flashdb",
                    "--slice-id",
                    "real-fdb-kv-set",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertEqual(translator_input["function_source_span"]["file"], "src/fdb_kvdb.c")
            self.assertEqual(translator_input["function_source_span"]["line_start"], 1369)
            dependency_names = {
                dependency["name"]
                for dependency in context_pack["call_edges"]
                if dependency.get("kind") == "callee"
            }
            self.assertEqual(
                dependency_names,
                {"strlen", "fdb_blob_make", "fdb_kv_set_blob", "fdb_kv_del"},
            )
            self.assertEqual(context_pack["direct_call_edges"], [])
            external_context = plan["inputs"]["external_callee_context"]
            self.assertEqual(external_context["status"], "recorded")
            self.assertEqual(external_context["declared_count"], 4)
            self.assertEqual(external_context["declared_spec_count"], 4)
            self.assertEqual(
                set(external_context["declared_spec_names"]),
                {"strlen", "fdb_blob_make", "fdb_kv_set_blob", "fdb_kv_del"},
            )
            self.assertEqual(external_context["blocked_count"], 0)
            self.assertEqual(
                {
                    item["name"]
                    for item in context_pack["external_direct_callee_declarations"]
                },
                {"strlen", "fdb_blob_make", "fdb_kv_set_blob", "fdb_kv_del"},
            )
            self.assertEqual(plan["translation_summary"]["external_direct_callee_blocks"], [])
            modeled_callees = {
                item["name"]: item
                for item in plan["translation_summary"]["external_direct_callees"]
            }
            self.assertEqual(
                set(modeled_callees),
                {"strlen", "fdb_blob_make", "fdb_kv_set_blob", "fdb_kv_del"},
            )
            self.assertIn("strlen", modeled_callees)
            self.assertEqual(modeled_callees["strlen"]["stub_kind"], "compile_only")
            self.assertEqual(modeled_callees["strlen"]["stub_boundary"], "stdlib_readonly_string_model")
            self.assertEqual(modeled_callees["strlen"]["return_type"], "size_t")
            self.assertEqual(modeled_callees["strlen"]["parameters"][0]["c_type"], "const char*")
            self.assertFalse(modeled_callees["strlen"]["semantics_verified"])
            self.assertIn("fdb_blob_make", modeled_callees)
            blob_make_binding = modeled_callees["fdb_blob_make"]["accepted_named_slice_evidence"]
            self.assertEqual(modeled_callees["fdb_blob_make"]["stub_kind"], "accepted_named_slice_evidence")
            self.assertEqual(modeled_callees["fdb_blob_make"]["stub_boundary"], "accepted_named_slice_context_only")
            self.assertFalse(modeled_callees["fdb_blob_make"]["semantics_verified"])
            self.assertEqual(blob_make_binding["target_id"], "flashdb")
            self.assertEqual(blob_make_binding["slice_id"], "real-fdb-blob-make")
            self.assertTrue(blob_make_binding["semantic_pass"])
            self.assertTrue(blob_make_binding["accepted_evidence_authoritative"])
            self.assertFalse(blob_make_binding["generated_draft_semantic_pass"])
            self.assertTrue(
                blob_make_binding["final_verification_path"].endswith(
                    "flashdb/auto-translation/real-fdb-blob-make/l3-real-fdb-blob-make-final-verification.json"
                )
            )
            for name in ("fdb_kv_del", "fdb_kv_set_blob"):
                self.assertEqual(modeled_callees[name]["stub_kind"], "compile_only")
                self.assertEqual(
                    modeled_callees[name]["stub_boundary"],
                    "flashdb_external_direct_callee_context_only",
                )
                self.assertEqual(
                    modeled_callees[name]["model_contract"],
                    "flashdb_external_direct_callee_signature_context",
                )
                self.assertFalse(modeled_callees[name]["semantics_verified"])
                self.assertEqual(modeled_callees[name]["unsupported_reasons"], [])
                self.assertEqual(
                    modeled_callees[name]["stub_generation"],
                    "not_emitted_flashdb_signature_context",
                )
            self.assertEqual(route["level"], "L4")
            self.assertEqual(route["status"], "refused")
            self.assertFalse(route["translator"]["candidate_generation_allowed"])
            self.assertEqual(route["rationale"][0]["feature"], "blocked_artifact")
            self.assertEqual(profile["status"], "blocked")
            self.assertFalse(profile["generated_draft_semantic_pass"])
            self.assertFalse(manifest["claim_boundary"]["semantic_pass"])
            self.assertFalse(manifest["claim_boundary"]["generated_draft_semantic_pass"])
            repair = blocked["blocked_repairs"][0]
            self.assertEqual(repair["ir_feature_gap"]["kind"], "blocked_artifact")
            self.assertEqual(repair["smallest_next_test"]["kind"], "route_refusal_regression")
            self.assertEqual(capability["status"], "recorded")
            self.assertEqual(json.loads(validation_result.stdout)["status"], "passed")
            self.assertEqual(capability["slice_id"], "real-fdb-kv-set")
            self.assertEqual(capability["capability_delta"][0]["construct_id"], "blocked_artifact")
            self.assertEqual(capability["capability_delta"][0]["generated_candidate_status"], "refused")
            self.assertFalse(capability["capability_delta"][0]["semantic_pass"])
            self.assertEqual(capability["capability_delta"][0]["blocked_callees"], [])
            self.assertTrue(capability["capability_delta"][0]["negative_coverage"])
            governance = capability["governance_delta"][0]
            self.assertEqual(governance["construct_id"], "blocked_artifact")
            self.assertTrue(
                any(
                    ref.endswith(
                        "flashdb/auto-translation/real-fdb-kv-set/l3-real-fdb-kv-set-route-decision.json"
                    )
                    for ref in governance["evidence_refs"]
                )
            )
            self.assertIn(
                "python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_unsupported_lvalue_blocks_auto_migrate_candidate_generation",
                capability["verification_commands"],
            )

    def test_real_fdb_kv_set_external_callees_accept_compile_context_only_signatures(self) -> None:
        module = load_auto_migrate_module()
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-kv-set.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))

        context = module.external_direct_callee_context(spec, None)

        self.assertEqual(context["status"], "recorded")
        self.assertEqual(context["declared_spec_count"], 4)
        self.assertEqual(context["declared_count"], 4)
        self.assertEqual(context["blocked_count"], 0)
        declared = {item["name"]: item for item in context["declared"]}
        self.assertEqual(
            set(declared),
            {"strlen", "fdb_blob_make", "fdb_kv_set_blob", "fdb_kv_del"},
        )
        for name in ("fdb_kv_del", "fdb_kv_set_blob"):
            self.assertEqual(declared[name]["stub_kind"], "compile_only")
            self.assertEqual(
                declared[name]["stub_boundary"],
                "flashdb_external_direct_callee_context_only",
            )
            self.assertEqual(
                declared[name]["model_contract"],
                "flashdb_external_direct_callee_signature_context",
            )
            self.assertFalse(declared[name]["semantics_verified"])
            self.assertEqual(declared[name]["unsupported_reasons"], [])
            self.assertEqual(
                declared[name]["stub_generation"],
                "not_emitted_flashdb_signature_context",
            )
            self.assertNotIn("accepted_named_slice_evidence", declared[name])

    def test_real_fdb_kv_set_oracle_harness_includes_flashdb_public_header_before_typedefs(self) -> None:
        module = load_auto_migrate_module()
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-kv-set.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()

            module.generate_oracle_harness_draft(spec, evidence_dir, skip=True)

            harness = (evidence_dir / "l3-real-fdb-kv-set-c-oracle-harness-draft.c").read_text(
                encoding="utf-8"
            )
            oracle = json.loads(
                (evidence_dir / "l3-real-fdb-kv-set-c-oracle-status.json").read_text(encoding="utf-8")
            )
            prototype = module.c_function_prototype(spec)
            self.assertIn("#include <flashdb.h>\n", harness)
            self.assertLess(harness.index("#include <flashdb.h>"), harness.index(prototype))
            self.assertEqual(oracle["harness_contract"]["oracle_harness_includes"], ["flashdb.h"])

    def test_real_fdb_kv_set_oracle_compile_links_flashdb_support_sources(self) -> None:
        module = load_auto_migrate_module()
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-kv-set.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()

            module.generate_oracle_harness_draft(spec, evidence_dir, skip=True)

            oracle = json.loads(
                (evidence_dir / "l3-real-fdb-kv-set-c-oracle-status.json").read_text(encoding="utf-8")
            )
            compile_command = oracle["compile_command_draft"]
            linked_paths = {item["path"] for item in compile_command["link_source_files"]}
            self.assertEqual(
                compile_command["link_strategy"],
                "compile_harness_with_declared_c_boundary_and_build_profile_sources",
            )
            self.assertTrue(
                {
                    "src/fdb_kvdb.c",
                    "src/fdb_utils.c",
                    "src/fdb.c",
                    "src/fdb_file.c",
                }.issubset(linked_paths)
            )
            argv_text = " ".join(compile_command["argv"])
            for path in ("src/fdb_utils.c", "src/fdb.c", "src/fdb_file.c"):
                self.assertIn(path, argv_text)

    def test_real_fdb_kv_set_oracle_harness_binds_uninitialized_return_code_cases(self) -> None:
        module = load_auto_migrate_module()
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-kv-set.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            fixture_path = tmp_path / "real-fdb-kv-set.json"
            fixture_path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "uninit-set-value",
                                "db_state": "uninitialized_named",
                                "db_name": "unit-kv",
                                "key": "boot_count",
                                "value": "123",
                                "return_code": 7,
                            },
                            {
                                "id": "uninit-delete-null",
                                "db_state": "uninitialized_named",
                                "db_name": "unit-kv",
                                "key": "boot_count",
                                "value": None,
                                "return_code": 7,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            fixture_ref = fixture_path.as_posix()
            spec["fixture_contract"] = {
                **spec["fixture_contract"],
                "path": fixture_ref,
                "cases": [
                    {
                        "id": "uninit-set-value",
                        "input_ref": "cases[0]",
                        "expected_ref": fixture_ref,
                    },
                    {
                        "id": "uninit-delete-null",
                        "input_ref": "cases[1]",
                        "expected_ref": fixture_ref,
                    },
                ],
            }
            evidence_dir = tmp_path / "evidence"
            evidence_dir.mkdir()

            module.generate_oracle_harness_draft(spec, evidence_dir, skip=True)

            harness = (evidence_dir / "l3-real-fdb-kv-set-c-oracle-harness-draft.c").read_text(
                encoding="utf-8"
            )
            oracle = json.loads(
                (evidence_dir / "l3-real-fdb-kv-set-c-oracle-status.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("TODO: fixture case", harness)
            self.assertIn("struct fdb_kvdb uninit_set_value_db = {0};", harness)
            self.assertIn("uninit_set_value_db.parent.name", harness)
            self.assertIn("fdb_kv_set(&uninit_set_value_db, uninit_set_value_key, uninit_set_value_value)", harness)
            self.assertIn("fdb_kv_set(&uninit_delete_null_db, uninit_delete_null_key, NULL)", harness)
            self.assertIn("fixture case uninit-set-value return_code matched", harness)
            self.assertIn("fixture case uninit-delete-null return_code matched", harness)
            self.assertEqual(oracle["fixture_binding"]["case_count"], 2)
            self.assertEqual(
                oracle["fixture_binding"]["expected_output_status"],
                "declared_not_executed",
            )

    def test_modeled_strlen_external_callee_does_not_emit_fake_i32_stub(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-stdlib-stub-") as tmp:
            draft_path = Path(tmp) / "draft.rs"
            draft_path.write_text("pub fn caller() -> i32 { 0 }\n", encoding="utf-8")

            changed = module.inject_external_callee_stubs(
                draft_path,
                {
                    "declared": [
                        {
                            "name": "strlen",
                            "parameters": [{"name": "s", "c_type": "const char*"}],
                            "return_type": "size_t",
                            "stub_kind": "compile_only",
                            "stub_generation": "not_emitted_modeled_stdlib",
                            "semantics_verified": False,
                        },
                        {
                            "name": "helper_add_one",
                            "parameters": [{"name": "value", "c_type": "int"}],
                            "return_type": "int",
                            "stub_kind": "compile_only",
                            "stub_generation": "generated_compile_only",
                            "semantics_verified": False,
                        },
                        {
                            "name": "fdb_kv_del",
                            "parameters": [
                                {
                                    "name": "db",
                                    "c_type": "fdb_kvdb_t",
                                    "rust_type": "*mut core::ffi::c_void",
                                },
                                {
                                    "name": "key",
                                    "c_type": "const char*",
                                    "rust_type": "*const core::ffi::c_char",
                                },
                            ],
                            "return_type": "fdb_err_t",
                            "return_rust_type": "i32",
                            "stub_kind": "compile_only",
                            "stub_generation": "not_emitted_flashdb_signature_context",
                            "semantics_verified": False,
                        },
                    ]
                },
            )

            text = draft_path.read_text(encoding="utf-8")
            self.assertTrue(changed)
            self.assertIn("fn helper_add_one(value: i32) -> i32", text)
            self.assertNotIn("fn strlen", text)
            self.assertNotIn("s: i32", text)
            self.assertNotIn("fn fdb_kv_del", text)
            self.assertNotIn("db: i32", text)

    def test_real_fdb_blob_make_generates_typed_ir_candidate_without_semantic_claim(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-blob-make.json"
        with tempfile.TemporaryDirectory(prefix="auto-migrate-real-fdb-blob-make-") as tmp:
            out_root = Path(tmp) / "evidence"

            result = subprocess.run(
                [
                    sys.executable,
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                    "--skip-rust-check",
                    "--emit-clang-lowering-report",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "flashdb" / "auto-translation" / "real-fdb-blob-make"
            prefix = "l3-real-fdb-blob-make"
            plan = json.loads((evidence_dir / f"{prefix}-auto-translation-plan.json").read_text(encoding="utf-8"))
            route = json.loads((evidence_dir / f"{prefix}-route-decision.json").read_text(encoding="utf-8"))
            profile = json.loads((evidence_dir / f"{prefix}-validation-profile.json").read_text(encoding="utf-8"))
            report = json.loads((evidence_dir / f"{prefix}-clang-lowering-report.json").read_text(encoding="utf-8"))
            draft = (evidence_dir / f"{prefix}-rust-draft.rs").read_text(encoding="utf-8")

            self.assertEqual(plan["translation_source"]["selected"], "clang-lowered-typed-ir")
            self.assertEqual(report["status"], "lowered")
            self.assertEqual(report["typed_ir_candidate"]["status"], "generated")
            self.assertTrue(report["typed_ir_candidate"]["rust_draft_generated"])
            self.assertEqual(route["level"], "L1")
            self.assertEqual(route["status"], "recorded")
            self.assertTrue(route["translator"]["candidate_generation_allowed"])
            self.assertEqual(
                route["candidate_generation"]["selected_candidate_id"],
                "primary:clang-lowered-typed-ir",
            )
            self.assertEqual(route["candidate_generation"]["typed_ir"]["status"], "generated")
            self.assertFalse(route["candidate_generation"]["generated_draft_semantic_pass"])
            self.assertEqual(profile["status"], "incomplete")
            self.assertFalse(profile["generated_draft_semantic_pass"])
            self.assertFalse(manifest["claim_boundary"]["semantic_pass"])
            self.assertFalse(manifest["claim_boundary"]["generated_draft_semantic_pass"])
            self.assertIn("pub struct FdbBlob", draft)
            self.assertIn("pub fn fdb_blob_make", draft)

    def test_real_fdb_blob_make_c_oracle_harness_binds_fixture_cases_without_semantic_claim(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-blob-make.json"
        with tempfile.TemporaryDirectory(prefix="auto-migrate-real-fdb-blob-make-c-oracle-") as tmp:
            out_root = Path(tmp) / "evidence"

            result = subprocess.run(
                [
                    sys.executable,
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                    "--skip-rust-check",
                    "--emit-clang-lowering-report",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "flashdb" / "auto-translation" / "real-fdb-blob-make"
            prefix = "l3-real-fdb-blob-make"
            oracle = json.loads((evidence_dir / f"{prefix}-c-oracle-status.json").read_text(encoding="utf-8"))
            harness = (evidence_dir / f"{prefix}-c-oracle-harness-draft.c").read_text(encoding="utf-8")

            self.assertEqual(oracle["status"], "SKIPPED_LOCAL_NO_C_TOOLCHAIN")
            self.assertFalse(oracle["semantic_pass"])
            self.assertFalse(manifest["claim_boundary"]["semantic_pass"])
            self.assertEqual(oracle["fixture_binding"]["case_count"], 3)
            self.assertEqual(oracle["fixture_binding"]["expected_output_status"], "declared_not_executed")
            self.assertEqual(
                oracle["compile_command_draft"]["link_strategy"],
                "compile_harness_with_embedded_slice_source",
            )
            self.assertNotIn("src/fdb_utils.c", " ".join(oracle["compile_command_draft"]["argv"]))
            self.assertIn("struct fdb_blob {", harness)
            self.assertIn("typedef struct fdb_blob *fdb_blob_t;", harness)
            self.assertIn(
                "fdb_blob_t fdb_blob_make(fdb_blob_t blob, const void *value_buf, size_t buf_len)\n{",
                harness,
            )
            self.assertLess(
                harness.index("typedef struct fdb_blob *fdb_blob_t;"),
                harness.index("fdb_blob_t fdb_blob_make(fdb_blob_t blob, const void *value_buf, size_t buf_len)\n{"),
            )
            self.assertLess(
                harness.index("fdb_blob_t fdb_blob_make(fdb_blob_t blob, const void *value_buf, size_t buf_len)\n{"),
                harness.index("int main(void)"),
            )
            self.assertIn("static const uint8_t nominal_bytes_value_buf[] = { 16u, 32u, 48u };", harness)
            self.assertIn(
                "static const uint8_t shorter_length_than_buffer_value_buf[] = { 170u, 187u, 204u, 221u };",
                harness,
            )
            self.assertIn("fdb_blob_make(&null_empty_blob, NULL, (size_t)0u)", harness)
            self.assertIn("fdb_blob_make(&nominal_bytes_blob, nominal_bytes_value_buf, (size_t)3u)", harness)
            self.assertIn(
                "fdb_blob_make(&shorter_length_than_buffer_blob, "
                "shorter_length_than_buffer_value_buf, (size_t)2u)",
                harness,
            )
            for case_id in ("null-empty", "nominal-bytes", "shorter-length-than-buffer"):
                for field in ("return_same_blob", "blob.buf", "blob.size"):
                    self.assertIn(f"fixture case {case_id} {field} matched", harness)
            self.assertNotIn("TODO: load fixture values", harness)
            self.assertNotIn("is not supported by this draft call generator", harness)

    def test_real_fdb_blob_make_rust_replay_passes_without_semantic_claim(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-blob-make.json"
        with tempfile.TemporaryDirectory(prefix="auto-migrate-real-fdb-blob-make-replay-") as tmp:
            out_root = Path(tmp) / "evidence"

            result = subprocess.run(
                [
                    sys.executable,
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                    "--emit-clang-lowering-report",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "flashdb" / "auto-translation" / "real-fdb-blob-make"
            prefix = "l3-real-fdb-blob-make"
            rust_check = json.loads((evidence_dir / "rust-check.json").read_text(encoding="utf-8"))
            profile = json.loads((evidence_dir / f"{prefix}-validation-profile.json").read_text(encoding="utf-8"))
            replay = json.loads((evidence_dir / f"{prefix}-test-translation-generated.json").read_text(encoding="utf-8"))
            rust_report = json.loads((evidence_dir / f"{prefix}-rust-report.json").read_text(encoding="utf-8"))
            config_profile = json.loads((evidence_dir / f"{prefix}-config-profile.json").read_text(encoding="utf-8"))
            final = json.loads((evidence_dir / f"{prefix}-final-verification.json").read_text(encoding="utf-8"))
            capability = json.loads((evidence_dir / f"{prefix}-capability-delta.json").read_text(encoding="utf-8"))
            expected_slice_spec_key = f"slice_spec_sha256={hashlib.sha256(spec_path.read_bytes()).hexdigest()}"

            self.assertEqual(rust_check["status"], "passed")
            self.assertEqual(replay["status"], "passed")
            self.assertTrue(replay["generated_draft_replay_pass"])
            self.assertFalse(replay["generated_draft_semantic_pass"])
            for keys in (
                replay["cache_invalidation_keys"],
                rust_report["replay"]["cache_invalidation_keys"],
                config_profile["cache_invalidation_keys"],
                manifest["replay"]["cache_invalidation_keys"],
            ):
                slice_spec_keys = [key for key in keys if str(key).startswith("slice_spec_sha256=")]
                self.assertEqual(slice_spec_keys, [expected_slice_spec_key])
            replay_execution = replay["replay_execution"]
            self.assertTrue((REPO_ROOT / replay_execution["stdout_log"]).exists())
            self.assertTrue((REPO_ROOT / replay_execution["stderr_log"]).exists())
            self.assertEqual(profile["required_gate_status"]["compile"], "passed")
            self.assertEqual(profile["required_gate_status"]["c_oracle_diff"], "SKIPPED_LOCAL_NO_C_TOOLCHAIN")
            self.assertFalse(profile["generated_draft_semantic_pass"])
            self.assertEqual(final["rust_check_status"], "passed")
            self.assertFalse(final["semantic_pass"])
            self.assertFalse(manifest["claim_boundary"]["semantic_pass"])
            self.assertFalse(manifest["claim_boundary"]["generated_draft_semantic_pass"])
            delta_ids = {item["construct_id"] for item in capability["capability_delta"]}
            self.assertIn("typed_ir_candidate_generated", delta_ids)
            self.assertIn("rust_replay_fixture_passed", delta_ids)
            replay_delta = next(
                item for item in capability["capability_delta"] if item["construct_id"] == "rust_replay_fixture_passed"
            )
            self.assertEqual(replay_delta["generated_candidate_status"], "candidate")
            self.assertFalse(replay_delta["semantic_pass"])

    def test_real_fdb_blob_make_accept_existing_evidence_refreshes_governance_summary(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-blob-make.json"
        with tempfile.TemporaryDirectory(prefix="auto-migrate-real-fdb-blob-make-accepted-") as tmp:
            out_root = Path(tmp) / "evidence"

            subprocess.run(
                [
                    sys.executable,
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--accept-existing-evidence",
                    "--emit-clang-lowering-report",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            evidence_dir = out_root / "flashdb" / "auto-translation" / "real-fdb-blob-make"
            prefix = "l3-real-fdb-blob-make"
            route = json.loads((evidence_dir / f"{prefix}-route-decision.json").read_text(encoding="utf-8"))
            governance_summary = route["candidate_generation"]["governance_summary"]
            self.assertEqual(route["level"], "L4")
            self.assertEqual(route["status"], "refused")
            self.assertEqual(governance_summary["route_level"], "L4")
            self.assertEqual(governance_summary["route_status"], "refused")
            self.assertFalse(governance_summary["candidate_generation_allowed"])

            validation_result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--target-id",
                    "flashdb",
                    "--slice-id",
                    "real-fdb-blob-make",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                    "--require-semantic-pass",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(
                validation_result.returncode,
                0,
                f"stdout:\n{validation_result.stdout}\nstderr:\n{validation_result.stderr}",
            )

    def test_pointer_index_lvalue_decision_flows_through_auto_migrate(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "fill-first",
            "source_commit": "1234567",
            "function_name": "fill_first",
            "c_source": "int fill_first(int* out, int value) { out[0] = value; return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "fill-first.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "fill-first"
            cfg = json.loads((evidence_dir / "l3-fill-first-cfg.json").read_text(encoding="utf-8"))
            pointer_graph = json.loads((evidence_dir / "l3-fill-first-pointer-graph.json").read_text(encoding="utf-8"))
            plan = json.loads((evidence_dir / "l3-fill-first-auto-translation-plan.json").read_text(encoding="utf-8"))
            block = cfg["functions"][0]["basic_blocks"][0]

            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertFalse(manifest["claim_boundary"]["semantic_pass"])
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertIn("bounded_pointer_index", block["lvalue_kinds"])
            self.assertTrue(
                any(decision["decision"] == "bounded_pointer_index" for decision in block["lvalue_decisions"])
            )
            self.assertTrue(
                any(
                    decision["decision"] == "bounded_pointer_index"
                    for decision in pointer_graph["pointer_decisions"]
                )
            )
            out_node = next(node for node in pointer_graph["pointer_nodes"] if node["id"] == "out")
            self.assertIn("out[0]", out_node["write_effects"])
            self.assertIn("bounded_pointer_index", out_node["boundary_decisions"])
            self.assertIn("bounded-pointer-index-write", plan["translation_summary"]["translation_rule_ids"])
            self.assertEqual(plan["translation_summary"]["lvalue_decision_counts"]["bounded_pointer_index"], 1)
            self.assertEqual(
                plan["translation_summary"]["pointer_boundary_decision_counts"]["bounded_pointer_index"], 1
            )

    def test_input_buffer_pointer_decision_flows_through_auto_migrate(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": "1234567",
            "function_name": "sum_i32_buffer",
            "c_source": "int sum_i32_buffer(const int* values, int len, int* out) { int total = 0; for (int i = 0; i < len; i++) { total = total + values[i]; } out[0] = total; return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["return_code", "status", "sum"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "sum-i32-buffer.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "sum-i32-buffer"
            cfg = json.loads((evidence_dir / "l3-sum-i32-buffer-cfg.json").read_text(encoding="utf-8"))
            pointer_graph = json.loads(
                (evidence_dir / "l3-sum-i32-buffer-pointer-graph.json").read_text(encoding="utf-8")
            )
            plan = json.loads(
                (evidence_dir / "l3-sum-i32-buffer-auto-translation-plan.json").read_text(encoding="utf-8")
            )
            block = cfg["functions"][0]["basic_blocks"][0]

            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertFalse(manifest["claim_boundary"]["semantic_pass"])
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertIn("bounded_input_buffer_read", block["statement_kinds"])
            self.assertTrue(
                any(decision["decision"] == "bounded_input_buffer" for decision in block["lvalue_decisions"])
            )
            self.assertTrue(
                any(
                    decision["decision"] == "bounded_input_buffer"
                    for decision in pointer_graph["pointer_decisions"]
                )
            )
            values_node = next(node for node in pointer_graph["pointer_nodes"] if node["id"] == "values")
            self.assertEqual(values_node["kind"], "buffer")
            self.assertEqual(values_node["buffer_role"], "input")
            self.assertEqual(values_node["length_companion"], "len")
            self.assertEqual(values_node["ownership_role"], "borrowed")
            self.assertEqual(values_node["mutability"], "read_only")
            self.assertIn("values[i]", values_node["read_effects"])
            self.assertIn("bounded_input_buffer", values_node["boundary_decisions"])
            out_node = next(node for node in pointer_graph["pointer_nodes"] if node["id"] == "out")
            self.assertIn("out[0]", out_node["write_effects"])
            self.assertIn("bounded-input-buffer-read", plan["translation_summary"]["translation_rule_ids"])
            self.assertEqual(plan["translation_summary"]["lvalue_decision_counts"]["bounded_input_buffer"], 1)
            self.assertEqual(
                plan["translation_summary"]["pointer_boundary_decision_counts"]["bounded_input_buffer"], 1
            )

    def test_pointer_arithmetic_input_read_flows_through_auto_migrate(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": "1234567",
            "function_name": "sum_i32_ptr_arith",
            "c_source": "int sum_i32_ptr_arith(const int* values, int len, int* out) { int total = 0; for (int i = 0; i < len; i++) { total = total + *(values + i); } out[0] = total; return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["return_code", "status", "sum"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "sum-i32-ptr-arith.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "sum-i32-ptr-arith"
            cfg = json.loads((evidence_dir / "l3-sum-i32-ptr-arith-cfg.json").read_text(encoding="utf-8"))
            pointer_graph = json.loads(
                (evidence_dir / "l3-sum-i32-ptr-arith-pointer-graph.json").read_text(encoding="utf-8")
            )
            plan = json.loads(
                (evidence_dir / "l3-sum-i32-ptr-arith-auto-translation-plan.json").read_text(
                    encoding="utf-8"
                )
            )
            block = cfg["functions"][0]["basic_blocks"][0]

            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertIn("bounded_input_buffer_read", block["statement_kinds"])
            self.assertIn("bounded_pointer_arithmetic_input_read", block["statement_kinds"])
            self.assertIn("bounded_pointer_arithmetic_input_buffer", block["lvalue_kinds"])
            self.assertTrue(
                any(
                    decision["decision"] == "bounded_pointer_arithmetic_input_read"
                    and decision["translation_rule_id"] == "bounded-pointer-arithmetic-input-read"
                    for decision in block["lvalue_decisions"]
                )
            )
            self.assertTrue(
                any(
                    decision["decision"] == "bounded_pointer_arithmetic_input_read"
                    and decision["translation_rule_id"] == "bounded-pointer-arithmetic-input-read"
                    for decision in pointer_graph["pointer_decisions"]
                )
            )
            values_node = next(node for node in pointer_graph["pointer_nodes"] if node["id"] == "values")
            self.assertIn("values[i]", values_node["read_effects"])
            self.assertIn("*(values + i)", values_node["read_effects"])
            self.assertIn("bounded_input_buffer", values_node["boundary_decisions"])
            self.assertIn("bounded_pointer_arithmetic_input_read", values_node["boundary_decisions"])
            self.assertIn("bounded-input-buffer-read", plan["translation_summary"]["translation_rule_ids"])
            self.assertIn(
                "bounded-pointer-arithmetic-input-read",
                plan["translation_summary"]["translation_rule_ids"],
            )
            self.assertEqual(
                plan["translation_summary"]["lvalue_decision_counts"][
                    "bounded_pointer_arithmetic_input_read"
                ],
                1,
            )
            self.assertEqual(
                plan["translation_summary"]["pointer_boundary_decision_counts"][
                    "bounded_pointer_arithmetic_input_read"
                ],
                1,
            )

    def test_pointer_arithmetic_output_write_flows_through_auto_migrate(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "fill-i32-ptr-arith-out",
            "source_commit": "1234567",
            "function_name": "fill_i32_ptr_arith_out",
            "c_source": "int fill_i32_ptr_arith_out(int* out, int len, int value) { for (int i = 0; i < len; i++) { *(out + i) = value; } return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["return_code", "status", "out_values"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "fill-i32-ptr-arith-out.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "fill-i32-ptr-arith-out"
            cfg = json.loads((evidence_dir / "l3-fill-i32-ptr-arith-out-cfg.json").read_text(encoding="utf-8"))
            pointer_graph = json.loads(
                (evidence_dir / "l3-fill-i32-ptr-arith-out-pointer-graph.json").read_text(
                    encoding="utf-8"
                )
            )
            plan = json.loads(
                (
                    evidence_dir / "l3-fill-i32-ptr-arith-out-auto-translation-plan.json"
                ).read_text(encoding="utf-8")
            )
            rust_draft = (evidence_dir / "l3-fill-i32-ptr-arith-out-rust-draft.rs").read_text(
                encoding="utf-8"
            )
            block = cfg["functions"][0]["basic_blocks"][0]

            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertIn("out: &mut [i32]", rust_draft)
            self.assertIn("out[i as usize] = value;", rust_draft)
            self.assertIn("bounded_pointer_arithmetic_output_write", block["statement_kinds"])
            self.assertIn("bounded_pointer_arithmetic_output_buffer", block["lvalue_kinds"])
            self.assertTrue(
                any(
                    decision["decision"] == "bounded_pointer_arithmetic_output_write"
                    and decision["translation_rule_id"] == "bounded-pointer-arithmetic-output-write"
                    for decision in block["lvalue_decisions"]
                )
            )
            self.assertTrue(
                any(
                    decision["decision"] == "bounded_pointer_arithmetic_output_write"
                    and decision["translation_rule_id"] == "bounded-pointer-arithmetic-output-write"
                    for decision in pointer_graph["pointer_decisions"]
                )
            )
            out_node = next(node for node in pointer_graph["pointer_nodes"] if node["id"] == "out")
            self.assertEqual(out_node["kind"], "buffer")
            self.assertEqual(out_node["buffer_role"], "output")
            self.assertEqual(out_node["length_companion"], "len")
            self.assertEqual(out_node["ownership_role"], "out_param")
            self.assertEqual(out_node["mutability"], "write_only")
            self.assertIn("out[i]", out_node["write_effects"])
            self.assertIn("*(out + i)", out_node["write_effects"])
            self.assertIn("bounded_pointer_arithmetic_output_write", out_node["boundary_decisions"])
            self.assertIn(
                "bounded-pointer-arithmetic-output-write",
                plan["translation_summary"]["translation_rule_ids"],
            )
            self.assertEqual(
                plan["translation_summary"]["lvalue_decision_counts"][
                    "bounded_pointer_arithmetic_output_write"
                ],
                1,
            )
            self.assertEqual(
                plan["translation_summary"]["pointer_boundary_decision_counts"][
                    "bounded_pointer_arithmetic_output_write"
                ],
                1,
            )

    def test_alias_sensitive_read_write_pointer_gate_flows_through_auto_migrate(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "copy-i32-alias-gate",
            "source_commit": "1234567",
            "function_name": "copy_i32_alias_gate",
            "c_source": "int copy_i32_alias_gate(const int* values, int len, int* out) { for (int i = 0; i < len; i++) { *(out + i) = *(values + i); } return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "c_boundary": {
                "pointer_contract": {
                    "input_buffers": [
                        {
                            "name": "values",
                            "c_type": "const int*",
                            "length_companion": "len",
                            "read_effects": ["*(values + i)", "values[i]"],
                        }
                    ],
                    "output_pointers": [
                        {
                            "name": "out",
                            "c_type": "int*",
                            "length_companion": "len",
                            "write_effects": ["*(out + i)", "out[i]"],
                        }
                    ],
                    "aliasing_proven": False,
                }
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["return_code", "status", "out_values"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "copy-i32-alias-gate.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "copy-i32-alias-gate"
            pointer_graph = json.loads(
                (evidence_dir / "l3-copy-i32-alias-gate-pointer-graph.json").read_text(encoding="utf-8")
            )
            plan = json.loads(
                (evidence_dir / "l3-copy-i32-alias-gate-auto-translation-plan.json").read_text(
                    encoding="utf-8"
                )
            )
            cache = json.loads(
                (evidence_dir / "l3-copy-i32-alias-gate-auto-cache-metadata.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertIn("alias_sensitive_state", pointer_graph["applicability"]["triggers"])
            self.assertEqual(pointer_graph["schema_version"], 2)
            self.assertEqual(pointer_graph["alias_sets"][0]["id"], "alias-set-1")
            self.assertEqual(pointer_graph["alias_sets"][0]["members"], ["values", "out"])
            self.assertEqual(pointer_graph["alias_sets"][0]["relationship"], "unknown_overlap")
            self.assertEqual(
                pointer_graph["alias_sets"][0]["evidence"],
                "c_boundary.pointer_contract.aliasing_proven=false",
            )
            self.assertEqual(pointer_graph["alias_contract"]["decision"], "requires_noalias_contract")
            self.assertFalse(pointer_graph["alias_contract"]["proven"])
            self.assertTrue(pointer_graph["alias_contract"]["requires_noalias"])
            self.assertEqual(pointer_graph["alias_risks"][0]["risk_level"], "unknown_alias")
            self.assertEqual(pointer_graph["alias_risks"][0]["gate_decision"], "requires_noalias_contract")
            self.assertIn("values", pointer_graph["alias_risks"][0]["pointer_nodes"])
            self.assertIn("out", pointer_graph["alias_risks"][0]["pointer_nodes"])
            effect_graph = pointer_graph["effect_graph"]
            read_effect = next(
                effect
                for effect in effect_graph["effects"]
                if effect["pointer_node"] == "values"
                and effect["kind"] == "read"
                and effect["expression"] == "values[i]"
            )
            write_effect = next(
                effect
                for effect in effect_graph["effects"]
                if effect["pointer_node"] == "out"
                and effect["kind"] == "write"
                and effect["expression"] == "out[i]"
            )
            self.assertTrue(
                any(
                    edge["from_effect"] == read_effect["id"]
                    and edge["to_effect"] == write_effect["id"]
                    and edge["relationship"] == "requires_noalias"
                    for edge in effect_graph["edges"]
                )
            )
            self.assertEqual(effect_graph["summary"]["reads"], ["values"])
            self.assertEqual(effect_graph["summary"]["writes"], ["out"])
            self.assertTrue(effect_graph["summary"]["alias_sensitive"])
            self.assertEqual(
                effect_graph["summary"]["alias_gate_decision"],
                "requires_noalias_contract",
            )
            self.assertTrue(
                any(
                    item["kind"] == "noalias"
                    and item["applies_to"] == ["values", "out"]
                    and item["required"]
                    for item in pointer_graph["safe_boundary_preconditions"]
                )
            )
            self.assertEqual(
                plan["translation_summary"]["alias_gate"]["decision"],
                "requires_noalias_contract",
            )
            self.assertEqual(
                manifest["claim_boundary"]["alias_gate"]["decision"],
                "requires_noalias_contract",
            )
            self.assertFalse(manifest["claim_boundary"]["alias_gate"]["complete_alias_safety"])
            self.assertIn("effect_graph", pointer_graph["cache_invalidation_keys"])
            self.assertIn("effect_graph_identity", cache["cache_input_fields"])
            self.assertEqual(cache["effect_graph_identity"]["alias_sensitive"], True)
            self.assertEqual(cache["effect_graph_identity"]["read_effect_count"], 2)
            self.assertEqual(cache["effect_graph_identity"]["write_effect_count"], 2)

    def test_output_only_pointer_write_does_not_trigger_input_output_alias_risk(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "fill-i32-output-only",
            "source_commit": "1234567",
            "function_name": "fill_i32_output_only",
            "c_source": "int fill_i32_output_only(int* out, int len, int value) { for (int i = 0; i < len; i++) { *(out + i) = value; } return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["return_code", "status", "out_values"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "fill-i32-output-only.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "fill-i32-output-only"
            pointer_graph = json.loads(
                (evidence_dir / "l3-fill-i32-output-only-pointer-graph.json").read_text(encoding="utf-8")
            )
            plan = json.loads(
                (evidence_dir / "l3-fill-i32-output-only-auto-translation-plan.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertNotIn("alias_sensitive_state", pointer_graph["applicability"]["triggers"])
            self.assertEqual(pointer_graph["schema_version"], 2)
            self.assertEqual(pointer_graph["alias_sets"], [])
            self.assertEqual(pointer_graph["alias_risks"], [])
            self.assertEqual(pointer_graph["alias_contract"]["decision"], "not_applicable")
            self.assertFalse(pointer_graph["alias_contract"]["requires_noalias"])
            effect_graph = pointer_graph["effect_graph"]
            self.assertFalse(any(effect["kind"] == "read" for effect in effect_graph["effects"]))
            self.assertTrue(
                any(
                    effect["pointer_node"] == "out"
                    and effect["kind"] == "write"
                    and effect["expression"] == "out[i]"
                    for effect in effect_graph["effects"]
                )
            )
            self.assertEqual(effect_graph["summary"]["reads"], [])
            self.assertEqual(effect_graph["summary"]["writes"], ["out"])
            self.assertFalse(effect_graph["summary"]["alias_sensitive"])
            self.assertEqual(effect_graph["summary"]["alias_gate_decision"], "not_applicable")
            self.assertEqual(plan["translation_summary"]["alias_gate"]["decision"], "not_applicable")
            self.assertEqual(manifest["claim_boundary"]["alias_gate"]["decision"], "not_applicable")

    def test_cache_identity_tracks_alias_gate_inputs(self) -> None:
        auto_migrate = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "copy-i32-alias-cache",
            "source_commit": "1234567",
            "function_name": "copy_i32_alias_cache",
            "c_source": "int copy_i32_alias_cache(const int* values, int len, int* out) { for (int i = 0; i < len; i++) { *(out + i) = *(values + i); } return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {"target_triple": "x86_64-unknown-linux-gnu"},
            "c_boundary": {
                "pointer_contract": {
                    "input_buffers": [
                        {
                            "name": "values",
                            "c_type": "const int*",
                            "length_companion": "len",
                            "read_effects": ["*(values + i)", "values[i]"],
                        }
                    ],
                    "output_pointers": [
                        {
                            "name": "out",
                            "c_type": "int*",
                            "length_companion": "len",
                            "write_effects": ["*(out + i)", "out[i]"],
                        }
                    ],
                    "aliasing_proven": False,
                }
            },
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            spec_path = Path(tmp) / "copy-i32-alias-cache.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            identity = auto_migrate.cache_identity(spec, spec_path)

            self.assertIn("alias_gate_identity", identity)
            self.assertEqual(identity["alias_gate_identity"]["decision"], "requires_noalias_contract")
            self.assertEqual(identity["alias_gate_identity"]["risk_count"], 1)
            self.assertFalse(identity["alias_gate_identity"]["aliasing_proven"])
            self.assertTrue(identity["alias_gate_identity"]["requires_noalias"])
            self.assertIn("effect_graph_identity", identity)
            self.assertEqual(identity["effect_graph_identity"]["read_effect_count"], 2)
            self.assertEqual(identity["effect_graph_identity"]["write_effect_count"], 2)
            self.assertTrue(identity["effect_graph_identity"]["alias_sensitive"])
            self.assertEqual(
                identity["effect_graph_identity"]["alias_gate_decision"],
                "requires_noalias_contract",
            )
            self.assertEqual(identity["c2rust_baseline_identity"]["status"], "missing")
            self.assertEqual(identity["route_decision_identity"]["status"], "missing")
            self.assertEqual(identity["validation_profile_identity"]["status"], "missing")

    def test_unsupported_lvalue_blocks_auto_migrate_candidate_generation(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "unbounded-index",
            "source_commit": "1234567",
            "function_name": "unbounded_index",
            "c_source": "int unbounded_index(int* out, int i, int value) { out[i] = value; return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "unbounded-index.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "unbounded-index"
            cfg = json.loads((evidence_dir / "l3-unbounded-index-cfg.json").read_text(encoding="utf-8"))
            plan = json.loads(
                (evidence_dir / "l3-unbounded-index-auto-translation-plan.json").read_text(encoding="utf-8")
            )
            route = json.loads((evidence_dir / "l3-unbounded-index-route-decision.json").read_text(encoding="utf-8"))
            profile = json.loads(
                (evidence_dir / "l3-unbounded-index-validation-profile.json").read_text(encoding="utf-8")
            )
            blocked = json.loads(
                (evidence_dir / "l3-unbounded-index-self-healing-blocked-repairs.json").read_text(encoding="utf-8")
            )
            block = cfg["functions"][0]["basic_blocks"][0]

            self.assertEqual(manifest["translator"]["status"], "blocked")
            self.assertEqual(plan["status"], "blocked")
            self.assertEqual(route["level"], "L4")
            self.assertEqual(route["status"], "refused")
            self.assertEqual(route["translator"]["kind"], "refuse")
            self.assertFalse(route["translator"]["candidate_generation_allowed"])
            self.assertEqual(profile["route_level"], "L4")
            self.assertEqual(profile["status"], "blocked")
            self.assertIn({"gate": "candidate_generation", "reason": "route_refused"}, profile["skipped_gates"])
            self.assertEqual(manifest["status"], "candidate_refused")
            self.assertFalse(manifest["claim_boundary"]["semantic_pass"])
            self.assertIsNone(manifest["accepted_evidence_binding"])
            self.assertTrue(
                all(artifact["status"] == "blocked" for artifact in plan["generated_artifacts"])
            )
            events = [
                json.loads(line)
                for line in (evidence_dir / "l3-unbounded-index-auto-translation-events.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            rust_draft_events = [
                event for event in events if event["event_kind"] == "rust_draft_generated"
            ]
            self.assertEqual(rust_draft_events[0]["status"], "blocked")
            self.assertEqual(manifest["replay"]["evidence_links"]["rust_draft"]["status"], "blocked")
            replay_evidence = json.loads(
                (evidence_dir / "l3-unbounded-index-test-translation-generated.json").read_text(encoding="utf-8")
            )
            self.assertEqual(replay_evidence["evidence_links"]["rust_draft"]["status"], "blocked")
            self.assertEqual(blocked["status"], "recorded")
            repair = blocked["blocked_repairs"][0]
            self.assertEqual(repair["ir_feature_gap"]["kind"], "unsupported_lvalue")
            self.assertEqual(repair["oracle_fixture_gap"]["status"], "not_blocking")
            self.assertEqual(
                [route["route"] for route in repair["candidate_routes"]],
                ["typed_ir", "c2rust", "llm", "manual"],
            )
            self.assertEqual(repair["smallest_next_test"]["kind"], "route_refusal_regression")
            self.assertIn("human_intervention_point", repair)
            self.assertEqual(plan["translation_summary"]["unsupported_lvalue_count"], 1)
            self.assertIn("unsupported_lvalue", block["lvalue_kinds"])
            self.assertTrue(
                any(decision["decision"] == "unsupported_lvalue" for decision in block["lvalue_decisions"])
            )

    def test_unsupported_control_flow_blocks_auto_migrate_candidate_generation(self) -> None:
        cfg_schema = json.loads(
            (REPO_ROOT / "validation/cfg-template/cfg.schema.json").read_text(encoding="utf-8")
        )
        cases = [
            (
                "goto-loop",
                "again",
                "goto",
                "int again(int x) { again: x++; if (x < 10) goto again; return x; }",
            ),
            (
                "switch-return",
                "choose",
                "switch",
                "int choose(int x) { switch (x) { case 1: return 1; default: return 0; } }",
            ),
        ]
        for slice_id, function_name, expected_kind, c_source in cases:
            with self.subTest(slice_id=slice_id), tempfile.TemporaryDirectory(
                prefix="auto-migrate-test-"
            ) as tmp:
                spec = {
                    "target_id": "demo",
                    "slice_id": slice_id,
                    "source_commit": "1234567",
                    "function_name": function_name,
                    "c_source": c_source,
                    "fixture_hash": "fixture",
                    "build_profile": {
                        "include_paths": [],
                        "defines": [],
                        "target_triple": "x86_64-unknown-linux-gnu",
                        "abi": "linux-gnu",
                        "compiler_command_source": "unit-test",
                        "clang_available": True,
                    },
                    "fixture_contract": {
                        "input": "unit-test-fixture.json",
                        "behavior_fields": ["value"],
                    },
                    "non_goals": ["unit test only"],
                }
                tmp_path = Path(tmp)
                spec_path = tmp_path / f"{slice_id}.json"
                spec_path.write_text(json.dumps(spec), encoding="utf-8")
                out_root = tmp_path / "evidence"

                result = subprocess.run(
                    [
                        "python",
                        str(AUTO_MIGRATE),
                        "--slice-spec",
                        str(spec_path),
                        "--out-root",
                        str(out_root),
                        "--skip-c-oracle",
                    ],
                    cwd=REPO_ROOT,
                    text=True,
                    capture_output=True,
                    check=True,
                )

                manifest = json.loads(result.stdout)
                evidence_dir = out_root / "demo" / "auto-translation" / slice_id
                prefix = f"l3-{slice_id}"
                cfg = json.loads((evidence_dir / f"{prefix}-cfg.json").read_text(encoding="utf-8"))
                jsonschema.Draft7Validator(cfg_schema).validate(cfg)
                plan = json.loads(
                    (evidence_dir / f"{prefix}-auto-translation-plan.json").read_text(encoding="utf-8")
                )
                route = json.loads(
                    (evidence_dir / f"{prefix}-route-decision.json").read_text(encoding="utf-8")
                )
                profile = json.loads(
                    (evidence_dir / f"{prefix}-validation-profile.json").read_text(encoding="utf-8")
                )
                blocked = json.loads(
                    (evidence_dir / f"{prefix}-self-healing-blocked-repairs.json").read_text(
                        encoding="utf-8"
                    )
                )

                self.assertEqual(cfg["status"], "blocked")
                self.assertTrue(cfg["unsupported_control_flow"])
                unsupported_kinds = {item["kind"] for item in cfg["unsupported_control_flow"]}
                self.assertTrue(any(item["kind"] == expected_kind for item in cfg["unsupported_control_flow"]))
                self.assertNotIn("unknown", unsupported_kinds)
                self.assertIn("relooper_refusal", unsupported_kinds)
                if expected_kind == "goto":
                    self.assertIn("label", unsupported_kinds)
                if expected_kind == "switch":
                    self.assertIn("case", unsupported_kinds)
                    self.assertIn("default", unsupported_kinds)
                structured = cfg["functions"][0]["structured_control_flow"]
                self.assertTrue(structured["relooper_required"])
                self.assertEqual(structured["has_goto"], expected_kind == "goto")
                self.assertEqual(structured["has_switch"], expected_kind == "switch")
                if expected_kind == "goto":
                    self.assertIn("goto_target_resolved", structured["relooper_preconditions"])
                    self.assertIn(
                        "goto_requires_structured_recovery",
                        structured["relooper_refusals"],
                    )
                if expected_kind == "switch":
                    self.assertIn(
                        "switch_cases_enumerated",
                        structured["relooper_preconditions"],
                    )
                    self.assertIn(
                        "switch_requires_structured_recovery",
                        structured["relooper_refusals"],
                    )
                self.assertIn("no Rust candidate lowering", structured["scope_note"])
                block_ids = {block["id"] for block in cfg["functions"][0]["basic_blocks"]}
                edge_pairs = {
                    (edge["from"], edge["to"], edge["kind"])
                    for edge in cfg["functions"][0]["edges"]
                }
                if expected_kind == "goto":
                    self.assertTrue({"label-again", "goto-again"}.issubset(block_ids))
                    self.assertIn(("entry", "label-again", "unsupported"), edge_pairs)
                    self.assertIn(("entry", "goto-again", "unsupported"), edge_pairs)
                    self.assertIn(("goto-again", "label-again", "unsupported"), edge_pairs)
                if expected_kind == "switch":
                    self.assertTrue({"switch-0", "case-1", "default"}.issubset(block_ids))
                    self.assertIn(("entry", "switch-0", "unsupported"), edge_pairs)
                    self.assertIn(("switch-0", "case-1", "unsupported"), edge_pairs)
                    self.assertIn(("switch-0", "default", "unsupported"), edge_pairs)
                self.assertEqual(manifest["translator"]["status"], "blocked")
                self.assertEqual(plan["status"], "blocked")
                self.assertEqual(route["level"], "L4")
                self.assertEqual(route["status"], "refused")
                self.assertEqual(route["translator"]["kind"], "refuse")
                self.assertFalse(route["translator"]["candidate_generation_allowed"])
                self.assertIn(
                    "unsupported_control_flow",
                    [item.get("feature") for item in route["rationale"]],
                )
                self.assertEqual(profile["route_level"], "L4")
                self.assertEqual(profile["status"], "blocked")
                self.assertIn({"gate": "candidate_generation", "reason": "route_refused"}, profile["skipped_gates"])
                self.assertEqual(manifest["status"], "candidate_refused")
                self.assertFalse(manifest["claim_boundary"]["semantic_pass"])
                self.assertIsNone(manifest["accepted_evidence_binding"])
                self.assertTrue(
                    all(artifact["status"] == "blocked" for artifact in plan["generated_artifacts"])
                )
                events = [
                    json.loads(line)
                    for line in (evidence_dir / f"{prefix}-auto-translation-events.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                    if line.strip()
                ]
                rust_draft_events = [
                    event for event in events if event["event_kind"] == "rust_draft_generated"
                ]
                self.assertEqual(rust_draft_events[0]["status"], "blocked")
                self.assertEqual(manifest["replay"]["evidence_links"]["rust_draft"]["status"], "blocked")
                replay_evidence = json.loads(
                    (evidence_dir / f"{prefix}-test-translation-generated.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(replay_evidence["evidence_links"]["rust_draft"]["status"], "blocked")
                self.assertEqual(blocked["status"], "recorded")
                repair = blocked["blocked_repairs"][0]
                self.assertEqual(repair["ir_feature_gap"]["kind"], "unsupported_control_flow")
                self.assertEqual(repair["oracle_fixture_gap"]["status"], "not_blocking")
                self.assertEqual(
                    [route["route"] for route in repair["candidate_routes"]],
                    ["typed_ir", "c2rust", "llm", "manual"],
                )
                self.assertEqual(repair["smallest_next_test"]["kind"], "route_refusal_regression")
                self.assertIn("human_intervention_point", repair)

    def test_l4_refused_accept_existing_evidence_keeps_generated_draft_blocked(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec = self._accepted_evidence_spec(tmp_path, include_toolchain_marker=True)
            spec.update(
                {
                    "target_id": "demo",
                    "slice_id": "unbounded-accepted",
                    "function_name": "unbounded_index",
                    "c_source": "int unbounded_index(int* out, int i, int value) { out[i] = value; return 0; }",
                    "build_profile": {
                        "include_paths": [],
                        "defines": [],
                        "target_triple": "x86_64-unknown-linux-gnu",
                        "abi": "linux-gnu",
                        "compiler_command_source": "unit-test",
                        "clang_available": True,
                    },
                    "non_goals": ["unit test only"],
                }
            )
            spec_path = tmp_path / "unbounded-accepted.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                    "--accept-existing-evidence",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "unbounded-accepted"
            replay_evidence = json.loads(
                (evidence_dir / "l3-unbounded-accepted-test-translation-generated.json").read_text(encoding="utf-8")
            )
            rust_report = json.loads(
                (evidence_dir / "l3-unbounded-accepted-rust-report.json").read_text(encoding="utf-8")
            )
            profile = json.loads(
                (evidence_dir / "l3-unbounded-accepted-validation-profile.json").read_text(encoding="utf-8")
            )
            final = json.loads(
                (evidence_dir / "l3-unbounded-accepted-final-verification.json").read_text(encoding="utf-8")
            )
            diff = json.loads((evidence_dir / "l3-unbounded-accepted-diff.json").read_text(encoding="utf-8"))
            negative = json.loads(
                (evidence_dir / "l3-unbounded-accepted-negative-diff.json").read_text(encoding="utf-8")
            )

            self.assertEqual(manifest["status"], "candidate_refused")
            self.assertFalse(manifest["semantic_pass"])
            self.assertFalse(manifest["claim_boundary"]["accepted_evidence_authoritative"])
            self.assertFalse(manifest["claim_boundary"]["generated_draft_semantic_pass"])
            self.assertEqual(manifest["route_decision"]["status"], "refused")
            self.assertEqual(manifest["replay"]["evidence_links"]["rust_draft"]["status"], "blocked")
            self.assertEqual(replay_evidence["evidence_links"]["rust_draft"]["status"], "blocked")
            self.assertEqual(rust_report["generated_draft"]["status"], "blocked")
            self.assertFalse(profile["accepted_evidence_authoritative"])
            self.assertFalse(profile["generated_draft_semantic_pass"])
            self.assertFalse(final["accepted_evidence_authoritative"])
            self.assertFalse(final["generated_draft_semantic_pass"])
            self.assertEqual(diff["diff_gate"], "schema_aware_c_rust_diff")
            self.assertEqual(diff["blocked_by"], [])
            self.assertTrue(diff["accepted_diff_required"])
            self.assertEqual(diff["required_inputs"]["c_oracle_actual_status"], "C_ORACLE_GENERATED")
            self.assertEqual(diff["required_inputs"]["rust_report_actual_status"], "passed")
            self.assertEqual(diff["required_inputs"]["schema_diff_actual_status"], "passed")
            self.assertIn("accepted_diff", diff)
            self.assertEqual(negative["negative_diff_gate"], "schema_aware_negative_diff")
            self.assertEqual(negative["blocked_by"], [])
            self.assertEqual(negative["root_blocked_by"], [])
            self.assertTrue(negative["accepted_negative_diff_required"])
            self.assertEqual(negative["required_inputs"]["schema_diff_actual_status"], "passed")
            self.assertIn("accepted_negative_diff", negative)

    def test_l4_refused_accept_existing_evidence_can_be_authoritative_when_requested(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec = self._accepted_evidence_spec(tmp_path, include_toolchain_marker=True)
            spec.update(
                {
                    "schema_version": 1,
                    "target_id": "demo",
                    "slice_id": "unbounded-authoritative",
                    "level": "L3",
                    "status": "ready",
                    "function_name": "unbounded_index",
                    "c_source": "int unbounded_index(int* out, int i, int value) { out[i] = value; return 0; }",
                    "l1_evidence": {
                        "path": "validation/evidence/demo/l1-native-build.json",
                        "status": "passed",
                        "accepted": True,
                    },
                    "source": {
                        "source_root": "<unit-test>",
                        "source_commit": "1234567",
                        "repo_commit": "workspace",
                    },
                    "c_boundary": {
                        "files": [{"path": "unit.c", "role": "source"}],
                        "functions": ["unbounded_index"],
                        "signatures": [
                            {
                                "function": "unbounded_index",
                                "return_type": "int",
                                "parameters": [
                                    {"name": "out", "c_type": "int*", "direction": "output"},
                                    {"name": "i", "c_type": "int", "direction": "input"},
                                    {"name": "value", "c_type": "int", "direction": "input"},
                                ],
                            }
                        ],
                    },
                    "build_profile": {
                        "profile_id": "demo-unbounded-authoritative",
                        "compiler_command_source": "unit-test",
                        "include_paths": [],
                        "defines": [],
                        "target": {
                            "triple_or_abi": "x86_64-unknown-linux-gnu",
                            "endianness": "little",
                            "int_width": 32,
                            "long_width": 64,
                            "pointer_width": 64,
                        },
                        "preprocessing_mode": "generated_stub",
                        "tool_versions": {},
                        "clang_type_extraction": {"available": True},
                    },
                    "claim_boundary": {
                        "accepted_evidence_authoritative": True,
                        "accepted_metadata_differences": [],
                        "non_goals": ["generated Rust draft is not accepted"],
                        "must_not_claim": ["semantic equivalence for the generated Rust draft"],
                    },
                    "rust_boundary": {
                        "crate": "validation/l2_slices",
                        "module": "validation/l2_slices/src/unbounded_authoritative.rs",
                        "public_api": [
                            {
                                "name": "unbounded_index",
                                "visibility": "public",
                                "boundary_kind": "safe_wrapper",
                            }
                        ],
                        "raw_pointer_policy": "internal_only",
                        "unsafe_policy": {
                            "max_first_party_non_test_ratio": 0.1,
                            "ledger_required": True,
                        },
                    },
                    "non_goals": ["unit test only"],
                    "cache_invalidation_keys": [
                        "source.source_commit",
                        "fixture_contract.hash",
                        "rust_boundary.module",
                    ],
                }
            )
            spec["fixture_contract"].update(
                {
                    "fixture_id": "unbounded-authoritative-fixture",
                    "hash": "fixture-hash",
                    "cases": [{"id": "case-one", "input_ref": "cases[0]", "expected_ref": spec["fixture_contract"]["c_oracle"]}],
                    "observable_outputs": ["value"],
                }
            )
            spec_path = tmp_path / "unbounded-authoritative.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                    "--accept-existing-evidence",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "unbounded-authoritative"
            route = json.loads(
                (evidence_dir / "l3-unbounded-authoritative-route-decision.json").read_text(encoding="utf-8")
            )
            profile = json.loads(
                (evidence_dir / "l3-unbounded-authoritative-validation-profile.json").read_text(encoding="utf-8")
            )
            final = json.loads(
                (evidence_dir / "l3-unbounded-authoritative-final-verification.json").read_text(encoding="utf-8")
            )
            final_path = evidence_dir / "l3-unbounded-authoritative-final-verification.json"

            self.assertEqual(manifest["status"], "accepted_evidence_bound")
            self.assertTrue(manifest["semantic_pass"])
            self.assertEqual(route["status"], "refused")
            self.assertEqual(route["level"], "L4")
            self.assertTrue(route["policy"]["accepted_evidence_authoritative"])
            self.assertFalse(route["policy"]["generated_draft_semantic_pass"])
            self.assertEqual(profile["status"], "passed")
            self.assertEqual(profile["route_level"], "L4")
            self.assertTrue(profile["accepted_evidence_authoritative"])
            self.assertFalse(profile["generated_draft_semantic_pass"])
            self.assertTrue(final["accepted_evidence_authoritative"])
            self.assertFalse(final["generated_draft_semantic_pass"])
            self.assertFalse(manifest["claim_boundary"]["generated_draft_semantic_pass"])
            contract = profile["oracle_boundary_contract"]
            self.assertEqual(contract["status"], "sufficient_for_semantic_pass")
            self.assertEqual(contract["observable_outputs"], ["value"])
            self.assertEqual(contract["fixture_representativeness"]["declared_case_count"], 1)
            self.assertEqual(contract["fixture_representativeness"]["accepted_oracle_case_count"], 1)
            self.assertEqual(contract["compiler"]["command_source"], "unit-test")
            self.assertEqual(contract["compiler"]["defines"], [])
            self.assertEqual(contract["target"]["triple_or_abi"], "x86_64-unknown-linux-gnu")
            self.assertEqual(contract["target"]["endianness"], "little")
            self.assertEqual(contract["target"]["word_size_bits"], 64)
            self.assertEqual(contract["sanitizer_diagnostics"]["sanitizer_status"], "not_run")
            self.assertEqual(contract["ub_and_implementation_defined"]["known_ub"], [])
            self.assertEqual(contract["ub_and_implementation_defined"]["implementation_defined_behavior"], [])
            self.assertEqual(contract["platform_model"]["hardware_dependency_status"], "not_applicable")
            self.assertEqual(contract["platform_model"]["rtos_dependency_status"], "not_applicable")
            self.assertEqual(contract["platform_model"]["volatile_dependency_status"], "not_applicable")
            self.assertEqual(final["oracle_boundary_contract"], contract)

            validation_result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "unbounded-authoritative",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                    "--require-semantic-pass",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(
                validation_result.returncode,
                0,
                f"stdout:\n{validation_result.stdout}\nstderr:\n{validation_result.stderr}",
            )
            self.assertTrue(json.loads(validation_result.stdout)["semantic_pass"])

            broken_final = dict(final)
            broken_final.pop("oracle_boundary_contract")
            final_path.write_text(json.dumps(broken_final), encoding="utf-8")
            manifest_path = evidence_dir / "l3-unbounded-authoritative-evidence-manifest.json"
            evidence_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            evidence_manifest["evidence"]["final_verification"]["sha256"] = hashlib.sha256(
                final_path.read_bytes()
            ).hexdigest()
            manifest_path.write_text(json.dumps(evidence_manifest), encoding="utf-8")
            broken_validation = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "unbounded-authoritative",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                    "--require-semantic-pass",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(broken_validation.returncode, 0)
            self.assertIn("oracle boundary contract", broken_validation.stderr + broken_validation.stdout)

    def test_compile_failure_records_blocked_patch_evidence(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "bad-syntax",
            "source_commit": "1234567",
            "function_name": "bad_syntax",
            "c_source": "int bad_syntax(int value) { return value + ; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "bad-syntax.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["rust_check"]["status"], "failed")
            self.assertEqual(manifest["patch"]["status"], "blocked")
            blocked_path = out_root / "demo" / "auto-translation" / "bad-syntax" / "l3-bad-syntax-self-healing-blocked-repairs.json"
            blocked = json.loads(blocked_path.read_text(encoding="utf-8"))
            self.assertEqual(blocked["status"], "recorded")
            repair = blocked["blocked_repairs"][0]
            self.assertEqual(repair["candidate_patch_id"], "patch-blocked-1")
            self.assertTrue(repair["human_action_required"])
            self.assertEqual(repair["ir_feature_gap"]["kind"], "rust_compile_failure")
            self.assertEqual(repair["oracle_fixture_gap"]["status"], "unknown_until_compile_passes")
            self.assertEqual(repair["smallest_next_test"]["kind"], "rust_compile_replay")
            self.assertIn("human_intervention_point", repair)

    def test_keyword_identifier_compile_failure_is_self_healed(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "keyword-param",
            "source_commit": "1234567",
            "function_name": "keyword_param",
            "c_source": "int keyword_param(int match) { return match + 1; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "keyword-param.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertEqual(manifest["patch"]["status"], "recorded")
            patch_events = (
                out_root
                / "demo"
                / "auto-translation"
                / "keyword-param"
                / "l3-keyword-param-patch-events.jsonl"
            ).read_text(encoding="utf-8")
            self.assertIn('"status": "verified"', patch_events)
            draft = (
                out_root
                / "demo"
                / "auto-translation"
                / "keyword-param"
                / "l3-keyword-param-rust-draft.rs"
            ).read_text(encoding="utf-8")
            self.assertIn("r#match", draft)

    def test_cache_drift_invalidates_reusable_translation_artifacts(self) -> None:
        auto_migrate = load_auto_migrate_module()
        previous = {
            "source_commit": "source-a",
            "source_file_hashes": {"src/file.c": "hash-a"},
            "slice_spec_sha256": "slice-a",
            "fixture_hash": "fixture-a",
            "build_profile_hash": "profile-a",
            "cargo_lock_hash": "lock-a",
            "tool_versions": {"rustc": "rustc-a"},
            "schema_versions": {"cfg": 1},
            "translator_version": "0.1.0",
            "translator_manifest_sha256": "manifest-a",
            "command_arguments": ["auto_migrate.py", "--slice-spec", "slice.json"],
            "alias_gate_identity": {
                "decision": "not_applicable",
                "risk_count": 0,
                "aliasing_proven": False,
                "requires_noalias": False,
            },
            "c2rust_baseline_identity": {"status": "skipped", "sha256": "baseline-a"},
            "route_decision_identity": {"status": "recorded", "sha256": "route-a"},
            "validation_profile_identity": {"status": "incomplete", "sha256": "profile-a"},
        }

        reusable = auto_migrate.cache_drift_report(previous, dict(previous))

        self.assertEqual(reusable["status"], "reusable")
        self.assertTrue(reusable["reuse_allowed"])
        self.assertEqual(reusable["invalidated_artifacts"], [])

        current = dict(previous)
        current["source_commit"] = "source-b"
        current["build_profile_hash"] = "profile-b"
        current["fixture_hash"] = "fixture-b"
        current["source_file_hashes"] = {"src/file.c": "hash-b"}
        current["alias_gate_identity"] = {
            "decision": "requires_noalias_contract",
            "risk_count": 1,
            "aliasing_proven": False,
            "requires_noalias": True,
        }
        current["c2rust_baseline_identity"] = {"status": "generated", "sha256": "baseline-b"}
        current["route_decision_identity"] = {"status": "recorded", "sha256": "route-b"}
        current["validation_profile_identity"] = {"status": "passed", "sha256": "profile-b"}

        drifted = auto_migrate.cache_drift_report(previous, current)

        self.assertEqual(drifted["status"], "drift_detected")
        self.assertFalse(drifted["reuse_allowed"])
        self.assertIn("source_commit", drifted["drifted_keys"])
        self.assertIn("source_file_hashes", drifted["drifted_keys"])
        self.assertIn("fixture_hash", drifted["drifted_keys"])
        self.assertIn("build_profile_hash", drifted["drifted_keys"])
        self.assertIn("alias_gate_identity", drifted["drifted_keys"])
        self.assertIn("c2rust_baseline_identity", drifted["drifted_keys"])
        self.assertIn("route_decision_identity", drifted["drifted_keys"])
        self.assertIn("validation_profile_identity", drifted["drifted_keys"])
        for artifact in [
            "context_pack",
            "type_map",
            "cfg",
            "pointer_graph",
            "c2rust_baseline",
            "route_decision",
            "validation_profile",
            "rust_draft",
            "patch_plan",
            "rust_replay",
            "c_oracle",
            "diff",
            "negative_diff",
            "unsafe_ledger",
            "final_verification",
            "auto_translation_manifest",
            "summary",
        ]:
            self.assertIn(artifact, drifted["invalidated_artifacts"])

    def test_accept_existing_evidence_requires_c_oracle_marker(self) -> None:
        auto_migrate = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            spec = self._accepted_evidence_spec(Path(tmp), include_toolchain_marker=False)

            with self.assertRaises(SystemExit) as raised:
                auto_migrate.resolve_accepted_evidence(spec)

            self.assertIn("toolchain_status=C_ORACLE_GENERATED", str(raised.exception))

    def test_accept_existing_evidence_binding_keeps_generated_draft_candidate(self) -> None:
        auto_migrate = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            spec = self._accepted_evidence_spec(Path(tmp), include_toolchain_marker=True)

            accepted = auto_migrate.resolve_accepted_evidence(spec)
            summary = auto_migrate.accepted_binding_summary(accepted)

            self.assertEqual(accepted["status"], "accepted")
            self.assertEqual(accepted["toolchain_status"], "C_ORACLE_GENERATED")
            self.assertFalse(accepted["generated_draft_semantic_pass"])
            self.assertFalse(summary["generated_draft_semantic_pass"])
            self.assertEqual(summary["paths"]["c_oracle"], accepted["paths"]["c_oracle"])

    def test_real_fdb_calc_crc32_accept_existing_evidence_with_unknown_target_boundary_stays_blocked(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            source_spec_path = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-calc-crc32.json"
            spec = json.loads(source_spec_path.read_text(encoding="utf-8"))
            target = spec.setdefault("build_profile", {}).setdefault("target", {})
            target["triple_or_abi"] = "unknown"
            target["endianness"] = "unknown"
            spec_path = tmp_path / "flashdb-real-fdb-calc-crc32-unknown-target.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = Path(tmp) / "evidence"
            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--accept-existing-evidence",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(
                result.returncode,
                0,
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "flashdb" / "auto-translation" / "real-fdb-calc-crc32"
            oracle = json.loads(
                (evidence_dir / "l3-real-fdb-calc-crc32-c-oracle-status.json").read_text(encoding="utf-8")
            )
            route = json.loads(
                (evidence_dir / "l3-real-fdb-calc-crc32-route-decision.json").read_text(encoding="utf-8")
            )
            profile = json.loads(
                (evidence_dir / "l3-real-fdb-calc-crc32-validation-profile.json").read_text(encoding="utf-8")
            )
            final = json.loads(
                (evidence_dir / "l3-real-fdb-calc-crc32-final-verification.json").read_text(encoding="utf-8")
            )

            self.assertEqual(manifest["status"], "candidate_refused")
            self.assertFalse(manifest["semantic_pass"])
            self.assertTrue(manifest["claim_boundary"]["accepted_evidence_authoritative"])
            self.assertFalse(manifest["claim_boundary"]["generated_draft_semantic_pass"])
            self.assertEqual(route["level"], "L4")
            self.assertEqual(route["status"], "refused")
            self.assertTrue(route["policy"]["accepted_evidence_authoritative"])
            self.assertEqual(profile["status"], "blocked")
            self.assertEqual(profile["profile"], "L4-accepted-evidence")
            contract = profile["oracle_boundary_contract"]
            self.assertEqual(contract["status"], "insufficient")
            self.assertIn("target_triple_or_abi_missing", contract["insufficient_reasons"])
            self.assertIn("target_endianness_missing", contract["insufficient_reasons"])
            self.assertIn(
                {
                    "gate": "oracle_boundary_contract",
                    "reason": "insufficient",
                    "insufficient": contract["insufficient_reasons"],
                },
                profile["skipped_gates"],
            )
            self.assertEqual(final["oracle_boundary_contract"], contract)
            self.assertEqual(final["status"], "incomplete")
            self.assertFalse(final["semantic_pass"])
            self.assertEqual(oracle["status"], "C_ORACLE_GENERATED")
            self.assertEqual(oracle["toolchain_status"], "C_ORACLE_GENERATED")
            self.assertEqual(oracle["global_linkage_requirements"][0]["name"], "crc32_table")
            self.assertEqual(
                oracle["harness_contract"]["global_dependencies"],
                oracle["global_linkage_requirements"],
            )

            validation_result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "flashdb",
                    "--slice-id",
                    "real-fdb-calc-crc32",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                    "--require-semantic-pass",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(validation_result.returncode, 0)
            self.assertIn("semantic pass requires manifest.status=passed", validation_result.stderr + validation_result.stdout)

    def test_real_fdb_calc_crc32_clang_typed_ir_translator_generates_candidate_route(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            out_root = Path(tmp) / "evidence"
            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-calc-crc32.json"),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                    "--emit-clang-lowering-report",
                ],
                cwd=REPO_ROOT,
                env=self._env_with_clang_path(),
                text=True,
                capture_output=True,
            )

            self.assertEqual(
                result.returncode,
                0,
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "flashdb" / "auto-translation" / "real-fdb-calc-crc32"
            route = json.loads(
                (evidence_dir / "l3-real-fdb-calc-crc32-route-decision.json").read_text(encoding="utf-8")
            )
            plan = json.loads(
                (evidence_dir / "l3-real-fdb-calc-crc32-auto-translation-plan.json").read_text(encoding="utf-8")
            )
            pointer = json.loads(
                (evidence_dir / "l3-real-fdb-calc-crc32-pointer-graph.json").read_text(encoding="utf-8")
            )
            rust_check = json.loads((evidence_dir / "rust-check.json").read_text(encoding="utf-8"))
            draft = (evidence_dir / "l3-real-fdb-calc-crc32-rust-draft.rs").read_text(encoding="utf-8")

            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertFalse(manifest["claim_boundary"]["semantic_pass"])
            self.assertEqual(route["status"], "recorded")
            self.assertEqual(route["level"], "L1")
            self.assertEqual(route["translator"]["kind"], "tier1")
            self.assertTrue(route["translator"]["candidate_generation_allowed"])
            self.assertEqual(plan["status"], "draft_generated")
            self.assertIn("clang-lowered-typed-ir", plan["translation_summary"]["translation_rule_ids"])
            self.assertIn("byte-cursor-loop", plan["translation_summary"]["translation_rule_ids"])
            self.assertEqual(pointer["pointer_nodes"][0]["symbol"], "buf")
            self.assertEqual(pointer["pointer_nodes"][0]["kind"], "buffer")
            self.assertEqual(pointer["pointer_nodes"][0]["buffer_role"], "input")
            self.assertEqual(pointer["pointer_nodes"][0]["length_companion"], "size")
            self.assertIn("byte_cursor_post_increment_read", pointer["pointer_nodes"][0]["boundary_decisions"])
            self.assertIn("CRC32_TABLE", draft)
            self.assertNotIn("crc32_update_byte", draft)
            self.assertNotIn("*p++", draft)
            self.assertEqual(rust_check["status"], "passed")

    def test_real_fdb_calc_crc32_translator_input_records_real_tu_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            out_root = Path(tmp) / "evidence"
            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-calc-crc32.json"),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(
                result.returncode,
                0,
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            evidence_dir = out_root / "flashdb" / "auto-translation" / "real-fdb-calc-crc32"
            translator_input = json.loads(
                (evidence_dir / "l3-real-fdb-calc-crc32-translator-input.json").read_text(encoding="utf-8")
            )

            self.assertEqual(
                translator_input["source_root"],
                "C:\\Users\\Administrator\\Documents\\c-to-rust\\sources\\FlashDB",
            )
            self.assertEqual(translator_input["source_file"], "src/fdb_utils.c")
            self.assertEqual(
                translator_input["source_file_hashes"],
                {
                    "src/fdb_utils.c": (
                        "207e1af49b7ee5cb26d31e66a0d8334bb3566b85bc727844be3c52fdbcf577cc"
                    )
                },
            )
            self.assertEqual(
                translator_input["source_files"],
                [
                    {
                        "path": "src/fdb_utils.c",
                        "role": "source",
                        "sha256": "207e1af49b7ee5cb26d31e66a0d8334bb3566b85bc727844be3c52fdbcf577cc",
                    }
                ],
            )
            self.assertEqual(
                translator_input["function_source_span"],
                {
                    "file": "src/fdb_utils.c",
                    "line_start": 77,
                    "line_end": 89,
                    "byte_start": 3818,
                    "byte_end": 4075,
                    "sha256": "523e88f41d20405f6aed4fbd62e1ddc2c7127473864d9ca80d2aca4874549007",
                },
            )
            self.assertNotIn("compile_commands", translator_input)
            self.assertEqual(
                translator_input["build_profile"]["compiler_command_source"],
                "C:\\Users\\Administrator\\Documents\\c-to-rust\\sources\\FlashDB\\CMakeLists.txt",
            )

    def test_translator_input_source_file_hashes_fall_back_to_c_boundary_files(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            spec = {
                "target_id": "demo",
                "slice_id": "hash-from-boundary",
                "source": {"source_root": "C:/missing/source/root"},
                "source_commit": "1234567",
                "function_name": "add_one",
                "c_source": "int add_one(int value) { return value + 1; }",
                "fixture_hash": "fixture-sha",
                "c_boundary": {
                    "files": [
                        {
                            "path": "src/add_one.c",
                            "role": "source",
                            "sha256": "declared-source-sha",
                        }
                    ],
                    "signatures": [
                        {
                            "function": "add_one",
                            "source_span": {
                                "file": "src/add_one.c",
                                "line_start": 1,
                                "line_end": 1,
                                "byte_start": 0,
                                "byte_end": 42,
                                "sha256": "span-sha",
                            },
                        }
                    ],
                },
                "build_profile": {
                    "include_paths": [],
                    "defines": [],
                    "compiler_command_source": "unit-test",
                },
            }
            spec_path = Path(tmp) / "slice.json"

            translator_spec = module.write_translator_spec(spec, spec_path, evidence_dir)
            translator_input = json.loads(translator_spec.read_text(encoding="utf-8"))

            self.assertEqual(
                translator_input["source_file_hashes"],
                {"src/add_one.c": "declared-source-sha"},
            )

    def test_translator_input_source_file_prefers_matching_function_span_file(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            spec = {
                "target_id": "demo",
                "slice_id": "multi-source-function-span",
                "source": {"source_root": "C:/src/project"},
                "source_commit": "1234567",
                "function_name": "target_fn",
                "c_source": "int target_fn(int value) { return value + 1; }",
                "fixture_hash": "fixture-sha",
                "c_boundary": {
                    "files": [
                        {
                            "path": "src/first_source.c",
                            "role": "source",
                            "sha256": "first-source-sha",
                        },
                        {
                            "path": "src/target_fn.c",
                            "role": "source",
                            "sha256": "target-source-sha",
                        },
                    ],
                    "signatures": [
                        {
                            "function": "target_fn",
                            "source_span": {
                                "file": "src/target_fn.c",
                                "line_start": 10,
                                "line_end": 12,
                                "byte_start": 100,
                                "byte_end": 160,
                                "sha256": "span-sha",
                            },
                        }
                    ],
                },
                "build_profile": {
                    "include_paths": [],
                    "defines": [],
                    "compiler_command_source": "unit-test",
                },
            }
            spec_path = Path(tmp) / "slice.json"

            translator_spec = module.write_translator_spec(spec, spec_path, evidence_dir)
            translator_input = json.loads(translator_spec.read_text(encoding="utf-8"))

            self.assertEqual(translator_input["source_file"], "src/target_fn.c")

    def test_translator_input_preserves_target_abi_profile(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            target = {
                "triple_or_abi": "x86_64-unknown-linux-gnu",
                "endianness": "little",
                "int_width": 32,
                "int_align": 32,
                "char_width": 8,
                "char_align": 8,
                "plain_char_signed": True,
                "short_width": 16,
                "short_align": 16,
                "long_width": 64,
                "long_align": 64,
                "long_long_width": 64,
                "long_long_align": 64,
                "pointer_width": 64,
                "pointer_align": 64,
            }
            spec = {
                "target_id": "demo",
                "slice_id": "target-abi-width",
                "source_commit": "1234567",
                "function_name": "count",
                "c_source": "size_t count(size_t value) { return value; }",
                "fixture_hash": "fixture-sha",
                "build_profile": {
                    "include_paths": [],
                    "defines": [],
                    "target": target,
                    "compiler_command_source": "unit-test",
                },
            }
            spec_path = Path(tmp) / "slice.json"

            translator_spec = module.write_translator_spec(spec, spec_path, evidence_dir)
            translator_input = json.loads(translator_spec.read_text(encoding="utf-8"))

            self.assertEqual(translator_input["build_profile"]["target"], target)
            self.assertEqual(
                translator_input["build_profile"]["target_triple"],
                "x86_64-unknown-linux-gnu",
            )
            self.assertEqual(
                translator_input["build_profile"]["abi"],
                "x86_64-unknown-linux-gnu",
            )

    def test_translator_input_preserves_scalar_arithmetic_contract(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            spec = {
                "target_id": "demo",
                "slice_id": "signed-rshift-contract",
                "source": {"source_root": "C:/src/project"},
                "source_commit": "1234567",
                "function_name": "signed_rshift_contract",
                "c_source": "int signed_rshift_contract(int value, int count) { return value >> count; }",
                "fixture_hash": "fixture-sha",
                "c_boundary": {
                    "scalar_arithmetic_contract": {
                        "wrapping_profile": "not_declared",
                        "signed_overflow": "not_declared",
                        "division_by_zero": "not_declared",
                        "signed_division_overflow": "not_declared",
                        "shift_count": "runtime_precondition_in_range",
                        "signed_right_shift": "explicit_implementation_defined_contract",
                    },
                    "files": [
                        {
                            "path": "src/signed_rshift_contract.c",
                            "role": "source",
                            "sha256": "declared-source-sha",
                        }
                    ],
                    "signatures": [
                        {
                            "function": "signed_rshift_contract",
                            "source_span": {
                                "file": "src/signed_rshift_contract.c",
                                "line_start": 1,
                                "line_end": 1,
                                "byte_start": 0,
                                "byte_end": 72,
                                "sha256": "span-sha",
                            },
                        }
                    ],
                },
                "build_profile": {
                    "include_paths": [],
                    "defines": [],
                    "compiler_command_source": "unit-test",
                },
            }
            spec_path = Path(tmp) / "slice.json"

            translator_spec = module.write_translator_spec(spec, spec_path, evidence_dir)
            translator_input = json.loads(translator_spec.read_text(encoding="utf-8"))

            self.assertEqual(
                translator_input["c_boundary"]["scalar_arithmetic_contract"]["signed_right_shift"],
                "explicit_implementation_defined_contract",
            )
            self.assertEqual(
                translator_input["c_boundary"]["scalar_arithmetic_contract"]["shift_count"],
                "runtime_precondition_in_range",
            )

    def test_run_translator_emit_clang_dry_run_enables_clang_frontend_feature(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            slice_spec = Path(tmp) / "translator-input.json"
            slice_spec.write_text("{}", encoding="utf-8")
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(
                    {
                        "target_id": "demo",
                        "slice_id": "add-one",
                        "status": "generated",
                        "artifact_paths": [],
                    }
                ),
                stderr="",
            )

            with mock.patch.object(module.subprocess, "run", return_value=completed) as run:
                module.run_translator(slice_spec, evidence_dir, emit_clang_dry_run=True)

            cmd = run.call_args.args[0]
            kwargs = run.call_args.kwargs
            self.assertIn("--features", cmd)
            self.assertIn("clang-frontend", cmd)
            self.assertLess(cmd.index("--features"), cmd.index("--bin"))
            self.assertEqual(kwargs["cwd"], module.REPO_ROOT)
            self.assertTrue(kwargs["text"])
            self.assertTrue(kwargs["capture_output"])

    def test_run_translator_emit_clang_dry_run_does_not_enable_lowering_report_feature(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            slice_spec = Path(tmp) / "translator-input.json"
            slice_spec.write_text("{}", encoding="utf-8")
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(
                    {
                        "target_id": "demo",
                        "slice_id": "add-one",
                        "status": "generated",
                        "artifact_paths": [],
                    }
                ),
                stderr="",
            )

            with mock.patch.object(module.subprocess, "run", return_value=completed) as run:
                module.run_translator(slice_spec, evidence_dir, emit_clang_dry_run=True)

            cmd = run.call_args.args[0]
            features = cmd[cmd.index("--features") + 1].split(",")
            self.assertEqual(features, ["clang-frontend"])
            self.assertNotIn("clang-lowering-report", features)

    def test_run_translator_default_does_not_enable_clang_features(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            slice_spec = Path(tmp) / "translator-input.json"
            slice_spec.write_text("{}", encoding="utf-8")
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(
                    {
                        "target_id": "demo",
                        "slice_id": "add-one",
                        "status": "generated",
                        "artifact_paths": [],
                    }
                ),
                stderr="",
            )

            with mock.patch.object(module.subprocess, "run", return_value=completed) as run:
                module.run_translator(slice_spec, evidence_dir)

            cmd = run.call_args.args[0]
            self.assertNotIn("--features", cmd)

    def test_run_translator_emit_clang_lowering_report_enables_report_feature(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            slice_spec = Path(tmp) / "translator-input.json"
            slice_spec.write_text("{}", encoding="utf-8")
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(
                    {
                        "target_id": "demo",
                        "slice_id": "add-one",
                        "status": "generated",
                        "artifact_paths": [],
                    }
                ),
                stderr="",
            )

            with mock.patch.object(module.subprocess, "run", return_value=completed) as run:
                module.run_translator(
                    slice_spec,
                    evidence_dir,
                    emit_clang_lowering_report=True,
                )

            cmd = run.call_args.args[0]
            self.assertIn("--features", cmd)
            features = cmd[cmd.index("--features") + 1].split(",")
            self.assertEqual(features, ["clang-lowering-report"])
            self.assertLess(cmd.index("--features"), cmd.index("--bin"))

    def test_cache_identity_records_emit_clang_dry_run_opt_in(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            spec_path = Path(tmp) / "slice.json"
            spec_path.write_text("{}", encoding="utf-8")
            spec = {
                "target_id": "demo",
                "slice_id": "add-one",
                "source": {"source_file_hashes": {"src/add_one.c": "source-sha"}},
                "fixture": {"sha256": "fixture-sha"},
                "build_profile": {},
            }

            identity = module.cache_identity(spec, spec_path, emit_clang_dry_run=True)

            self.assertIn("--emit-clang-dry-run", identity["command_arguments"])

    def test_cache_identity_keeps_clang_lowering_report_fields_out_by_default(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            spec_path = Path(tmp) / "slice.json"
            spec_path.write_text("{}", encoding="utf-8")
            spec = {
                "target_id": "demo",
                "slice_id": "add-one",
                "source": {"source_file_hashes": {"src/add_one.c": "source-sha"}},
                "fixture": {"sha256": "fixture-sha"},
                "build_profile": {},
            }

            identity = module.cache_identity(spec, spec_path, environment={})

            self.assertNotIn("--emit-clang-lowering-report", identity["command_arguments"])
            self.assertNotIn("translator_feature_set", identity)
            self.assertNotIn("clang_lowering_identity", identity)

    def test_cache_identity_records_emit_clang_lowering_report_opt_in(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            spec_path = Path(tmp) / "slice.json"
            spec_path.write_text("{}", encoding="utf-8")
            spec = {
                "target_id": "demo",
                "slice_id": "add-one",
                "source": {"source_file_hashes": {"src/add_one.c": "source-sha"}},
                "fixture": {"sha256": "fixture-sha"},
                "build_profile": {},
            }
            environment = {
                "CLANG_PATH": "C:/LLVM/bin/clang.exe",
                "LIBCLANG_PATH": "C:/LLVM/bin/libclang.dll",
            }

            with mock.patch.object(module, "command_version", return_value="clang version unit-test"):
                identity = module.cache_identity(
                    spec,
                    spec_path,
                    emit_clang_lowering_report=True,
                    environment=environment,
                )

            self.assertIn("--emit-clang-lowering-report", identity["command_arguments"])
            self.assertEqual(identity["translator_feature_set"], ["clang-lowering-report"])
            self.assertEqual(
                identity["clang_lowering_identity"],
                {
                    "enabled": True,
                    "frontend": "clang_ast_dump_json",
                    "command": "clang -Xclang -ast-dump=json -fsyntax-only",
                    "features": ["clang-lowering-report"],
                    "requires_env": ["CLANG_PATH"],
                    "clang_path_status": "configured",
                    "clang_path": "C:/LLVM/bin/clang.exe",
                    "ignored_env_for_ast_dump": {
                        "LIBCLANG_PATH": {
                            "status": "configured",
                            "value": "C:/LLVM/bin/libclang.dll",
                            "reason": "ignored_for_ast_dump",
                        },
                    },
                    "clang_version": "clang version unit-test",
                },
            )

    def test_cache_identity_records_competition_clang_lane(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            spec_path = Path(tmp) / "slice.json"
            spec_path.write_text("{}", encoding="utf-8")
            spec = {
                "target_id": "demo",
                "slice_id": "add-one",
                "source": {"source_file_hashes": {"src/add_one.c": "source-sha"}},
                "fixture": {"sha256": "fixture-sha"},
                "build_profile": {},
            }
            environment = {"CLANG_PATH": "/usr/bin/clang"}

            with mock.patch.object(module, "command_version", return_value="clang version unit-test"):
                identity = module.cache_identity(
                    spec,
                    spec_path,
                    competition_clang_lane=True,
                    environment=environment,
                )

            self.assertIn("--emit-clang-lowering-report", identity["command_arguments"])
            self.assertIn("--competition-clang-lane", identity["command_arguments"])
            self.assertEqual(identity["translator_feature_set"], ["clang-lowering-report"])
            self.assertTrue(identity["clang_lowering_identity"]["required"])
            self.assertEqual(identity["clang_lowering_identity"]["lane"], "competition-clang-lane")
            self.assertEqual(identity["clang_lowering_identity"]["requires_env"], ["CLANG_PATH"])
            self.assertEqual(identity["clang_lowering_identity"]["frontend"], "clang_ast_dump_json")
            self.assertEqual(
                identity["clang_lowering_identity"]["ignored_env_for_ast_dump"]["LIBCLANG_PATH"][
                    "reason"
                ],
                "ignored_for_ast_dump",
            )
            self.assertEqual(identity["clang_lowering_identity"]["clang_path_status"], "configured")

    def test_competition_clang_lane_accepts_project_local_clang(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            repo_root = Path(tmp)
            vendored = repo_root / "tools" / "llvm" / "bin" / "clang"
            vendored.parent.mkdir(parents=True)
            vendored.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            vendored.chmod(0o755)

            resolved = module.resolve_competition_clang_path(
                environment={}, repo_root=repo_root
            )

            self.assertEqual(resolved, ("tools/llvm/bin/clang", "vendored:tools/llvm/bin/clang"))

    def test_enrich_clang_lowering_report_records_durable_hashes(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-demo"
            function_ir = {"name": "demo", "body": [{"Return": {"expr": {"Literal": 1}}}]}
            report_path = evidence_dir / f"{prefix}-clang-lowering-report.json"
            draft_path = evidence_dir / f"{prefix}-rust-draft.rs"
            report_path.write_text(
                json.dumps(
                    {
                        "status": "lowered",
                        "typed_ir_candidate": {
                            "status": "generated",
                            "rust_draft_generated": True,
                        },
                        "lowering_report": {
                            "function_ir": function_ir,
                        },
                    }
                ),
                encoding="utf-8",
            )
            draft_path.write_text("pub fn demo() -> i32 { 1 }\n", encoding="utf-8")
            identity = {
                "clang_path": "/usr/bin/clang",
                "clang_version": "clang version unit-test",
                "frontend": "clang_ast_dump_json",
            }

            module.enrich_clang_lowering_report(evidence_dir, prefix, identity)

            enriched = json.loads(report_path.read_text(encoding="utf-8"))
            typed_ir_sha = module.sha256_json(function_ir)
            rust_draft_sha = hashlib.sha256(draft_path.read_bytes()).hexdigest()
            self.assertEqual(enriched["typed_ir_candidate"]["typed_ir_sha256"], typed_ir_sha)
            self.assertEqual(enriched["typed_ir_candidate"]["rust_draft_sha256"], rust_draft_sha)
            self.assertEqual(enriched["durable_evidence"]["hash_algorithm"], "sha256")
            self.assertEqual(enriched["durable_evidence"]["typed_ir_sha256"], typed_ir_sha)
            self.assertEqual(enriched["durable_evidence"]["rust_draft_sha256"], rust_draft_sha)
            self.assertEqual(enriched["durable_evidence"]["clang_path"], "/usr/bin/clang")
            self.assertEqual(enriched["durable_evidence"]["clang_version"], "clang version unit-test")
            self.assertEqual(
                enriched["durable_evidence"]["competition_environment"],
                module.competition_environment_identity(),
            )

    def test_real_fdb_calc_crc32_emit_clang_dry_run_opt_in_writes_temp_artifact(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            out_root = Path(tmp) / "evidence"
            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-calc-crc32.json"),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                    "--skip-rust-check",
                    "--emit-clang-dry-run",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(
                result.returncode,
                0,
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            evidence_dir = out_root / "flashdb" / "auto-translation" / "real-fdb-calc-crc32"
            dry_run = json.loads(
                (evidence_dir / "l3-real-fdb-calc-crc32-clang-dry-run.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(dry_run["frontend"], "clang")
            self.assertEqual(dry_run["artifact_kind"], "clang-dry-run")
            self.assertEqual(dry_run["status"], "diagnostic_only")
            self.assertEqual(dry_run["claim_boundary"]["role"], "diagnostic_only")
            self.assertEqual(dry_run["active_frontend"]["kind"], "clang_ast_dump_json")
            self.assertFalse(dry_run["active_frontend"]["uses_libclang"])
            self.assertEqual(dry_run["dry_run"]["source_file"], "src/fdb_utils.c")
            self.assertEqual(dry_run["dry_run"]["status"], "diagnostic_only")
            self.assertEqual(dry_run["errors"], [])

    def test_real_fdb_calc_crc32_emit_clang_lowering_report_opt_in_writes_temp_artifact(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            out_root = Path(tmp) / "evidence"
            environment = dict(os.environ)
            environment.pop("CLANG_PATH", None)
            environment.pop("LIBCLANG_PATH", None)
            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-calc-crc32.json"),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                    "--skip-rust-check",
                    "--emit-clang-lowering-report",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                env=environment,
            )

            self.assertEqual(
                result.returncode,
                0,
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            evidence_dir = out_root / "flashdb" / "auto-translation" / "real-fdb-calc-crc32"
            report = json.loads(
                (evidence_dir / "l3-real-fdb-calc-crc32-clang-lowering-report.json").read_text(
                    encoding="utf-8"
                )
            )
            cache = json.loads(
                (evidence_dir / "l3-real-fdb-calc-crc32-auto-cache-metadata.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(report["artifact_kind"], "clang-lowering-report")
            self.assertEqual(report["frontend"], "clang")
            self.assertEqual(report["status"], "unavailable")
            self.assertEqual(report["claim_boundary"]["role"], "diagnostic_only")
            self.assertFalse(report["claim_boundary"]["affects_manifest_status"])
            self.assertFalse(report["claim_boundary"]["affects_semantic_pass"])
            self.assertEqual(report["errors"][0]["kind"], "missing_clang_path")
            self.assertIn("--emit-clang-lowering-report", cache["command_arguments"])
            self.assertEqual(cache["translator_feature_set"], ["clang-lowering-report"])
            self.assertEqual(cache["clang_lowering_identity"]["enabled"], True)
            self.assertEqual(cache["clang_lowering_identity"]["clang_path_status"], "not_configured")
            self.assertIn("translator_feature_set", cache["cache_input_fields"])
            self.assertIn("clang_lowering_identity", cache["cache_input_fields"])

    def test_competition_clang_lane_requires_clang_path_or_project_local_clang(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            out_root = Path(tmp) / "evidence"
            environment = dict(os.environ)
            environment.pop("CLANG_PATH", None)
            environment.pop("LIBCLANG_PATH", None)
            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-calc-crc32.json"),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                    "--skip-rust-check",
                    "--competition-clang-lane",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                env=environment,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "competition clang lane requires CLANG_PATH or a project-local clang binary",
                result.stdout + result.stderr,
            )

    def test_cache_drift_invalidates_on_clang_lowering_report_identity_change(self) -> None:
        auto_migrate = load_auto_migrate_module()
        previous = {
            "source_commit": "source-a",
            "source_file_hashes": {"src/file.c": "hash-a"},
            "slice_spec_sha256": "slice-a",
            "fixture_hash": "fixture-a",
            "build_profile_hash": "profile-a",
            "cargo_lock_hash": "lock-a",
            "tool_versions": {"rustc": "rustc-a"},
            "schema_versions": {"cfg": 1},
            "translator_version": "0.1.0",
            "translator_manifest_sha256": "manifest-a",
            "command_arguments": ["auto_migrate.py", "--slice-spec", "slice.json"],
            "cache_input_fields": auto_migrate.CACHE_INPUT_FIELDS,
        }
        current = dict(previous)
        current["command_arguments"] = [
            "auto_migrate.py",
            "--slice-spec",
            "slice.json",
            "--emit-clang-lowering-report",
        ]
        current["cache_input_fields"] = auto_migrate.cache_input_fields(
            emit_clang_lowering_report=True
        )
        current["translator_feature_set"] = ["clang-lowering-report"]
        current["clang_lowering_identity"] = {
            "enabled": True,
            "frontend": "clang_ast_dump_json",
            "command": "clang -Xclang -ast-dump=json -fsyntax-only",
            "features": ["clang-lowering-report"],
            "requires_env": ["CLANG_PATH"],
            "clang_path_status": "configured",
            "clang_path": "C:/LLVM/bin/clang.exe",
            "ignored_env_for_ast_dump": {
                "LIBCLANG_PATH": {
                    "status": "configured",
                    "value": "C:/LLVM/bin/libclang.dll",
                    "reason": "ignored_for_ast_dump",
                },
            },
            "clang_version": "clang version unit-test",
        }

        drifted = auto_migrate.cache_drift_report(previous, current)

        self.assertEqual(drifted["status"], "drift_detected")
        self.assertIn("command_arguments", drifted["drifted_keys"])
        self.assertIn("translator_feature_set", drifted["drifted_keys"])
        self.assertIn("clang_lowering_identity", drifted["drifted_keys"])

    def test_real_fdb_calc_crc32_generated_replay_executes_candidate_fixture(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            out_root = Path(tmp) / "evidence"
            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-calc-crc32.json"),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                    "--emit-clang-lowering-report",
                ],
                cwd=REPO_ROOT,
                env=self._env_with_clang_path(),
                text=True,
                capture_output=True,
            )

            self.assertEqual(
                result.returncode,
                0,
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "flashdb" / "auto-translation" / "real-fdb-calc-crc32"
            test_translation = json.loads(
                (evidence_dir / "l3-real-fdb-calc-crc32-test-translation-generated.json").read_text(
                    encoding="utf-8"
                )
            )
            rust_report = json.loads(
                (evidence_dir / "l3-real-fdb-calc-crc32-rust-report.json").read_text(encoding="utf-8")
            )
            diff = json.loads((evidence_dir / "l3-real-fdb-calc-crc32-diff.json").read_text(encoding="utf-8"))
            replay_draft = (evidence_dir / "l3-real-fdb-calc-crc32-rust-replay-test-draft.rs").read_text(
                encoding="utf-8"
            )

            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertFalse(manifest["semantic_pass"])
            self.assertFalse(manifest["claim_boundary"]["generated_draft_semantic_pass"])
            self.assertIn("let actual = fdb_calc_crc32(case.crc, case.buf, case.size);", replay_draft)
            self.assertEqual(test_translation["status"], "passed")
            self.assertEqual(test_translation["replay_execution"]["status"], "passed")
            self.assertTrue(test_translation["generated_draft_replay_pass"])
            self.assertFalse(test_translation["generated_draft_semantic_pass"])
            self.assertEqual(rust_report["status"], "passed")
            self.assertFalse(rust_report["semantic_pass"])
            self.assertTrue(rust_report["generated_draft_replay_pass"])
            self.assertEqual(rust_report["case_count"], 2)
            self.assertEqual(rust_report["cases"][0]["id"], "empty-crc-zero")
            self.assertEqual(rust_report["cases"][1]["return_code"], 3421780262)
            self.assertEqual(diff["status"], "incomplete")
            self.assertEqual(diff["required_inputs"]["rust_report_actual_status"], "passed")

            validation = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "flashdb",
                    "--slice-id",
                    "real-fdb-calc-crc32",
                    "--slice-spec",
                    str(REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-calc-crc32.json"),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(
                validation.returncode,
                0,
                f"stdout:\n{validation.stdout}\nstderr:\n{validation.stderr}",
            )

    def test_real_fdb_calc_crc32_generated_replay_failure_stays_non_semantic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            fixture = json.loads(
                (REPO_ROOT / "validation" / "l2_slices" / "fixtures" / "real-fdb-calc-crc32.json").read_text(
                    encoding="utf-8"
                )
            )
            fixture["cases"][1]["return_code"] = 1
            fixture_path = tmp_path / "real-fdb-calc-crc32-wrong.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
            spec = json.loads(
                (REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-calc-crc32.json").read_text(
                    encoding="utf-8"
                )
            )
            spec["fixture_contract"]["path"] = fixture_path.as_posix()
            for case in spec["fixture_contract"]["cases"]:
                case["expected_ref"] = fixture_path.as_posix()
            spec_path = tmp_path / "flashdb-real-fdb-calc-crc32-wrong.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                    "--emit-clang-lowering-report",
                ],
                cwd=REPO_ROOT,
                env=self._env_with_clang_path(),
                text=True,
                capture_output=True,
            )

            self.assertEqual(
                result.returncode,
                0,
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "flashdb" / "auto-translation" / "real-fdb-calc-crc32"
            test_translation = json.loads(
                (evidence_dir / "l3-real-fdb-calc-crc32-test-translation-generated.json").read_text(
                    encoding="utf-8"
                )
            )
            rust_report = json.loads(
                (evidence_dir / "l3-real-fdb-calc-crc32-rust-report.json").read_text(encoding="utf-8")
            )
            diff = json.loads((evidence_dir / "l3-real-fdb-calc-crc32-diff.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertFalse(manifest["semantic_pass"])
            self.assertEqual(test_translation["status"], "failed")
            self.assertEqual(test_translation["replay_execution"]["status"], "failed")
            self.assertFalse(test_translation["generated_draft_replay_pass"])
            self.assertFalse(test_translation["generated_draft_semantic_pass"])
            self.assertEqual(rust_report["status"], "failed")
            self.assertFalse(rust_report["semantic_pass"])
            self.assertFalse(rust_report["generated_draft_replay_pass"])
            self.assertEqual(diff["status"], "incomplete")
            self.assertEqual(diff["required_inputs"]["rust_report_actual_status"], "failed")

    def test_promote_accepted_oracle_preserves_global_linkage_audit_fields(self) -> None:
        auto_migrate = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec = self._accepted_evidence_spec(tmp_path, include_toolchain_marker=True)
            global_dependency = {
                "kind": "global",
                "name": "table",
                "source": "unit-test",
                "definition_status": "same_file_top_level_declared",
                "source_span": {
                    "file": "unit.c",
                    "line_start": 1,
                    "line_end": 1,
                    "byte_start": 0,
                    "byte_end": 12,
                    "sha256": "table-sha",
                },
                "sha256": "table-sha",
            }
            spec["c_boundary"] = {
                "files": [{"path": "unit.c", "role": "source", "sha256": "unit-sha"}],
                "functions": ["demo_slice"],
                "signatures": [
                    {
                        "function": "demo_slice",
                        "return_type": "int",
                        "parameters": [],
                    }
                ],
                "direct_dependencies": [global_dependency],
            }
            expected_globals = auto_migrate.global_dependency_requirements(spec)
            draft_oracle = {
                "harness_draft": "validation/evidence/demo/auto-translation/demo-slice/l3-demo-slice-c-oracle-harness-draft.c",
                "harness_draft_ref": {"path": "draft.c", "sha256": "draft-sha", "status": "draft"},
                "fixture_binding": {"case_count": 1, "observable_outputs": ["value"]},
                "harness_contract": {
                    "function_prototype": "int demo_slice(void);",
                    "fixture": {"case_count": 1, "observable_outputs": ["value"]},
                    "source_files": spec["c_boundary"]["files"],
                    "global_dependencies": expected_globals,
                },
                "global_linkage_requirements": expected_globals,
                "compile_command_draft": {"status": "draft_not_executed"},
                "compile_execution": {"status": "compile_not_executed", "semantic_pass": False},
            }
            evidence_dir = tmp_path / "evidence"
            evidence_dir.mkdir()
            accepted = auto_migrate.resolve_accepted_evidence(spec)

            promoted = auto_migrate.promote_accepted_oracle(spec, evidence_dir, draft_oracle, accepted)

            self.assertEqual(promoted["status"], "C_ORACLE_GENERATED")
            self.assertEqual(promoted["global_linkage_requirements"], expected_globals)
            self.assertEqual(promoted["harness_contract"]["global_dependencies"], expected_globals)
            self.assertEqual(promoted["compile_command_draft"], draft_oracle["compile_command_draft"])
            self.assertEqual(promoted["compile_execution"], draft_oracle["compile_execution"])
            self.assertFalse(promoted["compile_execution"]["semantic_pass"])

    def test_source_file_hashes_preserve_generated_real_source_hashes(self) -> None:
        auto_migrate = load_auto_migrate_module()
        spec = {
            "source": {
                "source_root": "C:/external/FlashDB",
                "source_file_hashes": {
                    "src/fdb_utils.c": "real-source-sha",
                },
            },
            "c_boundary": {
                "files": [
                    {
                        "path": "src/fdb_utils.c",
                        "role": "source",
                        "sha256": "real-source-sha",
                    }
                ]
            },
        }

        hashes = auto_migrate.source_file_hashes(spec)

        self.assertEqual(hashes["src/fdb_utils.c"], "real-source-sha")

    def test_c2rust_baseline_manifest_records_tool_probe_without_generation_claim(self) -> None:
        auto_migrate = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "c2rust-probe",
            "source_commit": "1234567",
            "function_name": "add_one",
            "c_source": "int add_one(int x) { return x + 1; }",
            "fixture_hash": "fixture",
            "build_profile": {"compiler_command_source": "unit-test"},
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            evidence_dir = tmp_path / "evidence"
            evidence_dir.mkdir()
            slice_spec = tmp_path / "slice.json"
            slice_spec.write_text(json.dumps(spec), encoding="utf-8")

            with mock.patch.object(auto_migrate.shutil, "which", return_value=None):
                manifest = auto_migrate.emit_c2rust_baseline_manifest(
                    spec,
                    slice_spec,
                    evidence_dir,
                )

            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["status"], "skipped")
            self.assertEqual(manifest["reason"], "blocked_by_missing_tools")
            self.assertEqual(manifest["correctness_role"], "candidate_context_only")
            self.assertIsNone(manifest["selected_command"])
            self.assertIsNone(manifest["output"])
            self.assertEqual(manifest["tool_probe"]["path_search"], ["c2rust-transpile", "c2rust"])
            self.assertEqual(manifest["tool_probe"]["os_name"], os.name)
            self.assertTrue(manifest["tool_probe"]["diagnostic_only"])
            self.assertIn("environment_profile_hash", manifest["tool_probe"])
            self.assertEqual(manifest["reference_tree"]["path"], "tools/c2rust-reference")
            self.assertTrue(manifest["reference_tree"]["diagnostic_only"])
            self.assertIn("C2Rust output proves semantic equivalence", manifest["must_not_claim"])
            self.assertIn("C2Rust baseline was generated", manifest["must_not_claim"])

            schema = json.loads(
                (
                    REPO_ROOT
                    / "validation"
                    / "auto-translation-template"
                    / "c2rust-baseline-manifest.schema.json"
                ).read_text(encoding="utf-8")
            )
            jsonschema.validate(manifest, schema)

    def test_c2rust_reference_tree_can_be_configured_without_becoming_acceptance_evidence(self) -> None:
        auto_migrate = load_auto_migrate_module()
        with mock.patch.dict(os.environ, {"C2RUST_REFERENCE_TREE": "vendor/c2rust-src"}):
            reference_tree, configured = auto_migrate.resolve_c2rust_reference_tree()

        self.assertTrue(configured)
        self.assertEqual(reference_tree, REPO_ROOT / "vendor" / "c2rust-src")

    def test_c2rust_baseline_candidate_binding_never_semantic_pass(self) -> None:
        auto_migrate = load_auto_migrate_module()
        manifest_ref = {"path": "l3-demo-c2rust-baseline-manifest.json", "status": "skipped", "sha256": "abc"}

        binding = auto_migrate.c2rust_baseline_candidate_binding(
            {"status": "skipped", "reason": "blocked_by_missing_tools"},
            baseline_manifest_ref=manifest_ref,
        )

        self.assertEqual(binding["candidate_id"], "c2rust-baseline")
        self.assertEqual(binding["correctness_role"], "candidate_context_only")
        self.assertFalse(binding["semantic_pass"])
        self.assertFalse(binding["generated_draft_semantic_pass"])
        self.assertIsNone(binding["output_ref"])
        self.assertEqual(binding["baseline_manifest"], manifest_ref)

    def _accepted_evidence_spec(self, root: Path, include_toolchain_marker: bool) -> dict:
        fixture = root / "fixture.json"
        c_oracle = root / "c-oracle.json"
        rust_report = root / "rust-report.json"
        diff = root / "diff.json"
        negative = root / "negative-diff.json"
        unsafe_scan = root / "unsafe-scan.json"
        unsafe_ledger = root / "unsafe-ledger.json"
        fixture.write_text("[]\n", encoding="utf-8")
        oracle_payload = {
            "status": "passed",
            "source_commit": "1234567",
            "case_count": 1,
            "slice_id": "demo-slice",
        }
        if include_toolchain_marker:
            oracle_payload["toolchain_status"] = "C_ORACLE_GENERATED"
        c_oracle.write_text(json.dumps(oracle_payload), encoding="utf-8")
        rust_report.write_text(
            json.dumps({"status": "passed", "source_commit": "1234567", "case_count": 1}),
            encoding="utf-8",
        )
        diff.write_text(
            json.dumps({"status": "passed", "source_commit": "1234567", "first_mismatch": None}),
            encoding="utf-8",
        )
        negative.write_text(
            json.dumps(
                {
                    "status": "expected_failed",
                    "source_commit": "1234567",
                    "mutation_detected": True,
                    "first_mismatch": {"field": "value", "expected": 1, "actual": 2},
                }
            ),
            encoding="utf-8",
        )
        unsafe_scan.write_text(
            json.dumps({"status": "passed", "source_commit": "1234567", "first_party_non_test_unsafe_count": 0}),
            encoding="utf-8",
        )
        unsafe_ledger.write_text(
            json.dumps({"status": "passed", "source_commit": "1234567", "first_party_non_test_unsafe_count": 0}),
            encoding="utf-8",
        )
        return {
            "target_id": "demo",
            "slice_id": "demo-slice",
            "source_commit": "1234567",
            "fixture_hash": "fixture-hash",
            "fixture_contract": {
                "path": str(fixture),
                "c_oracle": str(c_oracle),
                "rust_report": str(rust_report),
                "diff": str(diff),
                "negative_diff": str(negative),
                "unsafe_scan": str(unsafe_scan),
                "unsafe_ledger": str(unsafe_ledger),
                "behavior_fields": ["value"],
            },
        }


if __name__ == "__main__":
    unittest.main()
