class _AutoMigrateTestsPart00:
    def _env_with_clang_path(self) -> dict[str, str]:
        environment = dict(os.environ)
        if environment.get("CLANG_PATH"):
            return environment
        default_clang = Path("C:/Program Files/LLVM/bin/clang.exe")
        if not default_clang.exists():
            self.skipTest("CLANG_PATH is required for real clang-lowering-report generation tests")
        environment["CLANG_PATH"] = str(default_clang)
        return environment

    def _assert_route_refused_candidate(
        self,
        manifest: dict[str, Any],
        evidence_dir: Path,
        slice_id: str,
        *,
        rust_status: str | None = "passed",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        prefix = f"l3-{slice_id}"
        route = json.loads((evidence_dir / f"{prefix}-route-decision.json").read_text(encoding="utf-8"))
        plan = json.loads((evidence_dir / f"{prefix}-auto-translation-plan.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["status"], "candidate_refused")
        self.assertFalse(manifest["claim_boundary"]["semantic_pass"])
        self.assertEqual(route["status"], "refused")
        self.assertEqual(route["level"], "L4")
        self.assertEqual(route["translator"]["kind"], "refuse")
        self.assertFalse(route["translator"]["candidate_generation_allowed"])
        self.assertIn("blocked_artifact", [item.get("feature") for item in route["rationale"]])
        self.assertEqual(plan["status"], "blocked")
        self.assertTrue(all(artifact["status"] == "blocked" for artifact in plan["generated_artifacts"]))
        if rust_status is not None:
            self.assertEqual(manifest["rust_check"]["status"], rust_status)
        return route, plan

    def test_write_text_preserves_lf_bytes_for_hash_stable_evidence(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            output_path = Path(tmp) / "evidence.json"

            module.write_text(output_path, "{\n  \"status\": \"recorded\"\n}\n")

            self.assertEqual(output_path.read_bytes(), b'{\n  "status": "recorded"\n}\n')

    def test_incomplete_manifest_does_not_make_openspec_a_semantic_gate(self) -> None:
        module = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            root = Path(tmp)
            evidence_dir = root / "evidence"
            evidence_dir.mkdir()
            slice_spec_path = root / "slice.json"
            spec = {
                "target_id": "demo",
                "slice_id": "store-add-one",
                "source_commit": "abc123",
                "fixture_contract": {"path": "fixtures/demo.json", "hash": "fixture-sha"},
            }
            slice_spec_path.write_text(json.dumps(spec), encoding="utf-8")

            manifest = module.emit_manifest(
                spec,
                evidence_dir,
                slice_spec_path,
                translator_summary={"status": "generated"},
                oracle={"status": "draft"},
                replay={"status": "not_run"},
                rust_check={"status": "blocked"},
                patch={"status": "not_run"},
                cache={"status": "recorded"},
                c2rust_baseline={"status": "skipped"},
                route_decision={
                    "level": "L1",
                    "status": "recorded",
                    "translator": {"candidate_generation_allowed": True},
                },
                validation_profile={"status": "blocked", "skipped_gates": ["rust_check"]},
            )

            self.assertNotIn("OpenSpec validation", manifest["claim_boundary"]["must_still_pass"])
            l3_manifest = json.loads(
                (evidence_dir / "l3-store-add-one-evidence-manifest.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("OpenSpec", l3_manifest["claim_boundary"]["scope"])

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
