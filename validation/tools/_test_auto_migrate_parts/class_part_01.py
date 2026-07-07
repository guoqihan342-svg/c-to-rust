class _AutoMigrateTestsPart01:
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
            route, plan = self._assert_route_refused_candidate(
                manifest,
                evidence_dir,
                "route-profile",
            )
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
            self.assertEqual(manifest["route_decision"]["level"], "L4")
            self.assertEqual(manifest["validation_profile"]["profile"], "L4-dev")
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
