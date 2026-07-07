class _ValidateAutoTranslationEvidenceTestsPart00:
    def test_sha256_uses_lf_stable_text_hashing_for_json_refs(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_bytes(b"{\"status\":\"passed\"}\r\n")

            expected = hashlib.sha256(b"{\"status\":\"passed\"}\n").hexdigest()

            self.assertEqual(module.sha256(path), expected)

    def _c2rust_compile_fixture(self, tmp_path: Path) -> tuple[dict, dict, Path]:
        output_file = tmp_path / "c2rust-baseline-output.rs"
        artifact_file = tmp_path / "c2rust-baseline-output.rlib"
        stdout_log = tmp_path / "rustc.stdout.log"
        stderr_log = tmp_path / "rustc.stderr.log"
        output_file.write_text("pub fn generated() {}\n", encoding="utf-8")
        artifact_file.write_text("fake rlib\n", encoding="utf-8")
        stdout_log.write_text("rustc ok\n", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        output_ref = {
            "path": output_file.as_posix(),
            "status": "generated",
            "sha256": self._sha256(output_file),
        }
        baseline = {
            "compile": {
                "status": "passed",
                "attempted": True,
                "semantic_pass": False,
                "candidate_output": dict(output_ref),
                "command": {
                    "argv": ["rustc", "--crate-type", "lib", output_file.as_posix()],
                    "working_directory": tmp_path.as_posix(),
                    "stdout_log": stdout_log.as_posix(),
                    "stderr_log": stderr_log.as_posix(),
                    "timeout_seconds": 60,
                    "exit_status": "passed",
                    "returncode": 0,
                },
                "artifact": {
                    "path": artifact_file.as_posix(),
                    "status": "compiled",
                    "sha256": self._sha256(artifact_file),
                },
                "diagnostics": [],
            }
        }
        return baseline, output_ref, tmp_path / "c2rust-baseline-manifest.json"

    def test_auto_translation_event_schema_accepts_translation_fallback_event(self) -> None:
        module = load_validator_module()
        schema = module.load_json(REPO_ROOT / "validation/auto-translation-template/auto-translation-event.schema.json")
        event = {
            "schema_version": 1,
            "event_id": "demo-slice-translation-fallback",
            "timestamp_utc": "2026-06-24T00:00:00Z",
            "target_id": "demo",
            "slice_id": "slice",
            "event_kind": "translation_fallback",
            "status": "recorded",
            "message": "Rust draft provenance recorded a compatibility fallback translator path.",
            "selected": "legacy-string-translator",
            "fallback_from": "clang-lowered-typed-ir",
            "fallback_reason": "clang_lowered_typed_ir_unavailable",
            "artifact_refs": [{"path": "plan.json", "status": "recorded"}],
        }

        jsonschema.validate(event, schema)

    def test_generated_candidate_diff_boundary_remains_non_semantic(self) -> None:
        module = load_validator_module()
        slice_spec = {
            "fixture_contract": {
                "observable_outputs": ["return_code"],
                "behavior_fields": ["return_code"],
            }
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
                        "status": "matched_not_oracle",
                        "semantic_pass": False,
                        "compared_fields": ["return_code"],
                        "matched_stdout_fragments": ["fixture case case-zero return_code matched"],
                        "missing_stdout_fragments": [],
                    },
                },
            },
        }
        rust_report = {
            "status": "passed",
            "semantic_pass": False,
            "generated_draft_replay_pass": True,
            "generated_draft_semantic_pass": False,
            "replay": {"status": "passed"},
        }
        report = {
            "generated_candidate_diff_pass": True,
            "blocked_by": ["accepted_c_oracle"],
            "required_inputs": {
                "c_oracle_actual_status": "DRAFT_GENERATED",
                "c_oracle_actual_toolchain_status": "COMPILE_SUCCEEDED_NOT_ORACLE",
                "c_oracle_output_gate_actual_status": "matched_not_oracle",
                "rust_replay_actual_status": "passed",
                "rust_report_actual_status": "passed",
            },
            "candidate_diff": {
                "status": "matched_not_oracle",
                "semantic_pass": False,
                "c_oracle_output_gate_status": "matched_not_oracle",
                "rust_replay_status": "passed",
                "missing_stdout_fragments": [],
                "matched_stdout_fragments": ["fixture case case-zero return_code matched"],
                "compared_fields": ["return_code"],
            },
        }

        module.validate_generated_candidate_diff_boundary(report, slice_spec, Path("diff.json"), oracle, rust_report)

        drifted = json.loads(json.dumps(report))
        drifted["candidate_diff"]["semantic_pass"] = True
        with self.assertRaises(SystemExit) as raised:
            module.validate_generated_candidate_diff_boundary(drifted, slice_spec, Path("diff.json"), oracle, rust_report)
        self.assertIn("candidate_diff cannot claim semantic_pass", str(raised.exception))

    def test_schema_diff_contract_rejects_candidate_diff_when_oracle_output_gate_drifts(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            evidence_dir = tmp_path / "evidence"
            evidence_dir.mkdir()
            slice_spec_path = tmp_path / "slice-spec.json"
            slice_spec_path.write_text(
                json.dumps(
                    {
                        "fixture_contract": {
                            "observable_outputs": ["return_code"],
                            "behavior_fields": ["return_code"],
                        }
                    }
                ),
                encoding="utf-8",
            )
            prefix = "l3-candidate-diff"
            matched_fragment = "fixture case case-zero return_code matched"
            diff = {
                "status": "incomplete",
                "semantic_pass": False,
                "diff_gate": "schema_aware_c_rust_diff",
                "accepted_diff_required": True,
                "blocked_by": ["accepted_c_oracle"],
                "first_mismatch": None,
                "compared_fields": ["return_code"],
                "generated_candidate_diff_pass": True,
                "required_inputs": {
                    "c_oracle_required_status": "C_ORACLE_GENERATED",
                    "rust_report_required_status": "passed",
                    "c_oracle_actual_status": "DRAFT_GENERATED",
                    "c_oracle_actual_toolchain_status": "COMPILE_SUCCEEDED_NOT_ORACLE",
                    "c_oracle_output_gate_actual_status": "matched_not_oracle",
                    "rust_replay_actual_status": "passed",
                    "rust_report_actual_status": "passed",
                },
                "candidate_diff": {
                    "status": "matched_not_oracle",
                    "semantic_pass": False,
                    "c_oracle_output_gate_status": "matched_not_oracle",
                    "rust_replay_status": "passed",
                    "missing_stdout_fragments": [],
                    "matched_stdout_fragments": [matched_fragment],
                    "compared_fields": ["return_code"],
                },
            }
            negative = {
                "status": "incomplete",
                "semantic_pass": False,
                "negative_diff_gate": "schema_aware_negative_diff",
                "expected_failure": True,
                "mutation_detected": False,
                "accepted_negative_diff_required": True,
                "blocked_by": ["schema_diff"],
                "required_inputs": {
                    "schema_diff_required_status": "passed",
                    "schema_diff_actual_status": "incomplete",
                },
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
                            "status": "matched_not_oracle",
                            "semantic_pass": False,
                            "compared_fields": ["return_code"],
                            "matched_stdout_fragments": [matched_fragment],
                            "missing_stdout_fragments": [],
                        },
                    },
                },
            }
            rust_report = {
                "status": "passed",
                "semantic_pass": False,
                "generated_draft_replay_pass": True,
                "generated_draft_semantic_pass": False,
                "replay": {"status": "passed"},
            }
            (evidence_dir / f"{prefix}-diff.json").write_text(json.dumps(diff), encoding="utf-8")
            (evidence_dir / f"{prefix}-negative-diff.json").write_text(json.dumps(negative), encoding="utf-8")
            (evidence_dir / f"{prefix}-c-oracle-status.json").write_text(json.dumps(oracle), encoding="utf-8")
            (evidence_dir / f"{prefix}-rust-report.json").write_text(json.dumps(rust_report), encoding="utf-8")

            module.validate_schema_diff_contract(evidence_dir, prefix, slice_spec_path)

            oracle["compile_execution"]["harness_execution"]["output_gate"]["status"] = "mismatch_not_oracle"
            (evidence_dir / f"{prefix}-c-oracle-status.json").write_text(json.dumps(oracle), encoding="utf-8")
            with self.assertRaises(SystemExit) as raised:
                module.validate_schema_diff_contract(evidence_dir, prefix, slice_spec_path)
            self.assertIn("candidate_diff output gate drift", str(raised.exception))

    def test_rejects_missing_route_profile_reference_in_final_verification(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            final_path = evidence_dir / "l3-adler32-step-final-verification.json"
            final = json.loads(final_path.read_text(encoding="utf-8"))
            final.pop("validation_profile", None)
            final_path.write_text(json.dumps(final), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--target-id",
                    "zlib-ng",
                    "--slice-id",
                    "adler32-step",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("final_verification.validation_profile", result.stderr + result.stdout)

    def test_rejects_missing_c2rust_baseline_reference_in_l3_manifest(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            manifest_path = evidence_dir / "l3-adler32-step-evidence-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["evidence"].pop("c2rust_baseline", None)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--target-id",
                    "zlib-ng",
                    "--slice-id",
                    "adler32-step",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("c2rust_baseline", result.stderr + result.stdout)

    def test_rejects_route_decision_ref_sha_drift(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            manifest_path = evidence_dir / "l3-adler32-step-evidence-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["evidence"]["route_decision"]["sha256"] = "wrong-sha"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--target-id",
                    "zlib-ng",
                    "--slice-id",
                    "adler32-step",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("sha256", result.stderr + result.stdout)

    def test_rejects_route_source_artifact_ref_sha_drift(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            route_path = evidence_dir / "l3-adler32-step-route-decision.json"
            route = json.loads(route_path.read_text(encoding="utf-8"))
            route["source_artifacts"]["translation_plan"]["sha256"] = "stale-plan-sha"
            route_path.write_text(json.dumps(route), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--target-id",
                    "zlib-ng",
                    "--slice-id",
                    "adler32-step",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("route_decision.source_artifacts.translation_plan", result.stderr + result.stdout)

    def test_validates_typed_ir_candidate_binding_against_clang_lowering_report(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-real-fdb-calc-crc32"
            report_path = evidence_dir / f"{prefix}-clang-lowering-report.json"
            report_candidate = {
                "status": "generated",
                "candidate_route": {
                    "route_id": "generic-typed-ir",
                    "route": "GenericTypedIr",
                    "candidate_generator": "GenericTypedIrEmitter",
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
                    },
                    {
                        "code": "signed_right_shift_implementation_defined",
                        "detail": "signed right shift requires an explicit implementation-defined contract",
                        "ir_node": "IrExpr::Binary.Shr",
                        "source_span": None,
                    }
                ],
                "rust_draft_generated": True,
                "typed_ir_sha256": "typed-ir-sha",
                "rust_draft_sha256": "rust-draft-sha",
                "semantic_pass": False,
            }
            self._write_json(
                report_path,
                {
                    "status": "lowered",
                    "typed_ir_candidate": report_candidate,
                },
            )
            typed_ir = dict(report_candidate)
            typed_ir["source_artifact"] = self._ref(report_path, "lowered")
            typed_ir["readonly_globals_identity"] = {
                "count": 1,
                "names": ["crc32_table"],
                "sha256": hashlib.sha256(
                    json.dumps(report_candidate["readonly_globals"], sort_keys=True).encode("utf-8")
                ).hexdigest(),
            }
            typed_ir["scalar_admission"] = {
                "status": "covered",
                "precondition_count": 2,
                "covered": [
                    {
                        "code": "shift_count_in_range",
                        "status": "covered",
                        "covered_by": [
                            "c_boundary.scalar_arithmetic_contract.shift_count",
                            "fixture_contract.scalar_input_domain",
                        ],
                    },
                    {
                        "code": "signed_right_shift_implementation_defined",
                        "status": "covered",
                        "covered_by": [
                            "c_boundary.scalar_arithmetic_contract.signed_right_shift",
                            "fixture_contract.scalar_input_domain",
                        ],
                    }
                ],
                "unresolved": [],
                "contract_status": "recorded",
                "source_fields": [
                    "c_boundary.scalar_arithmetic_contract",
                    "fixture_contract.scalar_input_domain",
                    "claim_boundary.must_not_claim",
                ],
            }
            route = {
                "source_artifacts": {
                    "clang_lowering_report": self._ref(report_path, "lowered"),
                },
                "candidate_generation": {"typed_ir": typed_ir},
                "scalar_ub_contract": {
                    "status": "recorded",
                    "c_boundary": {
                        "wrapping_profile": "not_declared",
                        "signed_overflow": "runtime_precondition_no_overflow",
                        "division_by_zero": "runtime_precondition_nonzero_divisor",
                        "signed_division_overflow": "runtime_precondition_excludes_min_div_minus_one",
                        "shift_count": "runtime_precondition_in_range",
                        "signed_right_shift": "explicit_implementation_defined_contract",
                    },
                    "fixture_contract": {
                        "case_source": "unit-test",
                        "parameters": [{"name": "size", "type": "size_t", "range": [0, 1024]}],
                        "covers_overflow_boundaries": False,
                    },
                    "claim_boundary": {"must_not_claim": []},
                },
            }
            profile = {"candidate_generation": route["candidate_generation"]}

            module.validate_typed_ir_candidate_binding(evidence_dir, prefix, route, profile)

            drifted = json.loads(json.dumps(route))
            drifted["candidate_generation"]["typed_ir"]["candidate_route"]["route"] = "Unsupported"
            with self.assertRaises(SystemExit) as raised:
                module.validate_typed_ir_candidate_binding(
                    evidence_dir,
                    prefix,
                    drifted,
                    {"candidate_generation": drifted["candidate_generation"]},
                )
            self.assertIn("typed_ir", str(raised.exception))

            semantic_claim = json.loads(json.dumps(route))
            semantic_claim["candidate_generation"]["typed_ir"]["semantic_pass"] = True
            with self.assertRaises(SystemExit) as raised:
                module.validate_typed_ir_candidate_binding(
                    evidence_dir,
                    prefix,
                    semantic_claim,
                    {"candidate_generation": semantic_claim["candidate_generation"]},
                )
            self.assertIn("semantic_pass", str(raised.exception))

            runtime_drift = json.loads(json.dumps(route))
            runtime_drift["candidate_generation"]["typed_ir"]["runtime_preconditions"][0][
                "code"
            ] = "division_divisor_nonzero"
            with self.assertRaises(SystemExit) as raised:
                module.validate_typed_ir_candidate_binding(
                    evidence_dir,
                    prefix,
                    runtime_drift,
                    {"candidate_generation": runtime_drift["candidate_generation"]},
                )
            self.assertIn("clang-lowering-report", str(raised.exception))

            hash_drift = json.loads(json.dumps(route))
            hash_drift["candidate_generation"]["typed_ir"]["typed_ir_sha256"] = "wrong-typed-ir-sha"
            with self.assertRaises(SystemExit) as raised:
                module.validate_typed_ir_candidate_binding(
                    evidence_dir,
                    prefix,
                    hash_drift,
                    {"candidate_generation": hash_drift["candidate_generation"]},
                )
            self.assertIn("typed_ir", str(raised.exception))

            admission_drift = json.loads(json.dumps(route))
            admission_drift["candidate_generation"]["typed_ir"]["scalar_admission"]["status"] = "unresolved"
            with self.assertRaises(SystemExit) as raised:
                module.validate_typed_ir_candidate_binding(
                    evidence_dir,
                    prefix,
                    admission_drift,
                    {"candidate_generation": admission_drift["candidate_generation"]},
                )
            self.assertIn("scalar_admission", str(raised.exception))

            contract_drift = json.loads(json.dumps(route))
            contract_drift.pop("scalar_ub_contract")
            with self.assertRaises(SystemExit) as raised:
                module.validate_typed_ir_candidate_binding(
                    evidence_dir,
                    prefix,
                    contract_drift,
                    {"candidate_generation": contract_drift["candidate_generation"]},
                )
            self.assertIn("scalar_admission", str(raised.exception))

            missing_admission = json.loads(json.dumps(route))
            missing_admission["candidate_generation"]["typed_ir"].pop("scalar_admission")
            with self.assertRaises(SystemExit) as raised:
                module.validate_typed_ir_candidate_binding(
                    evidence_dir,
                    prefix,
                    missing_admission,
                    {"candidate_generation": missing_admission["candidate_generation"]},
                )
            self.assertIn("scalar_admission", str(raised.exception))

    def test_rejects_unsupported_typed_ir_candidate_reason_drift(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-unsupported-typed-ir"
            report_path = evidence_dir / f"{prefix}-clang-lowering-report.json"
            report_candidate = {
                "status": "unsupported",
                "candidate_route": {
                    "route_id": "unsupported",
                    "route": "Unsupported",
                    "candidate_generator": "None",
                    "reasons": [
                        {
                            "code": "unsupported",
                            "detail": "call expressions are not supported by typed IR emitter",
                        }
                    ],
                },
                "readonly_globals": [],
                "rust_draft_generated": False,
                "semantic_pass": False,
                "unsupported_reason": "call expressions are not supported by typed IR emitter",
            }
            self._write_json(report_path, {"status": "lowered", "typed_ir_candidate": report_candidate})
            typed_ir = dict(report_candidate)
            typed_ir["source_artifact"] = self._ref(report_path, "lowered")
            typed_ir["readonly_globals_identity"] = {
                "count": 0,
                "names": [],
                "sha256": hashlib.sha256(json.dumps([], sort_keys=True).encode("utf-8")).hexdigest(),
            }
            route = {
                "source_artifacts": {"clang_lowering_report": self._ref(report_path, "lowered")},
                "candidate_generation": {"typed_ir": typed_ir},
            }
            profile = {"candidate_generation": route["candidate_generation"]}

            module.validate_typed_ir_candidate_binding(evidence_dir, prefix, route, profile)

            drifted = json.loads(json.dumps(route))
            drifted["candidate_generation"]["typed_ir"].pop("unsupported_reason")
            drifted_profile = {"candidate_generation": drifted["candidate_generation"]}
            with self.assertRaises(SystemExit) as raised:
                module.validate_typed_ir_candidate_binding(evidence_dir, prefix, drifted, drifted_profile)
            self.assertIn("typed_ir", str(raised.exception))
            self.assertIn("clang-lowering-report", str(raised.exception))

    def test_rejects_unsupported_typed_ir_candidate_missing_from_report(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-unsupported-typed-ir"
            report_path = evidence_dir / f"{prefix}-clang-lowering-report.json"
            self._write_json(report_path, {"status": "lowered"})
            typed_ir = {
                "status": "unsupported",
                "source_artifact": self._ref(report_path, "lowered"),
                "candidate_route": {
                    "route_id": "unsupported",
                    "route": "Unsupported",
                    "candidate_generator": "None",
                },
                "readonly_globals": [],
                "readonly_globals_identity": {
                    "count": 0,
                    "names": [],
                    "sha256": hashlib.sha256(json.dumps([], sort_keys=True).encode("utf-8")).hexdigest(),
                },
                "rust_draft_generated": False,
                "semantic_pass": False,
                "unsupported_reason": "call expressions are not supported by typed IR emitter",
            }
            route = {
                "source_artifacts": {"clang_lowering_report": self._ref(report_path, "lowered")},
                "candidate_generation": {"typed_ir": typed_ir},
            }
            profile = {"candidate_generation": route["candidate_generation"]}

            with self.assertRaises(SystemExit) as raised:
                module.validate_typed_ir_candidate_binding(evidence_dir, prefix, route, profile)
            self.assertIn("typed IR candidate evidence missing", str(raised.exception))

    def test_rejects_typed_ir_candidate_reference_boundary_gaps(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-real-fdb-calc-crc32"
            report_path = evidence_dir / f"{prefix}-clang-lowering-report.json"
            report_candidate = {
                "status": "generated",
                "candidate_route": {
                    "route_id": "generic-typed-ir",
                    "route": "GenericTypedIr",
                    "candidate_generator": "GenericTypedIrEmitter",
                },
                "readonly_globals": [{"name": "crc32_table"}],
                "rust_draft_generated": True,
                "semantic_pass": False,
            }
            self._write_json(report_path, {"status": "lowered", "typed_ir_candidate": report_candidate})
            typed_ir = dict(report_candidate)
            typed_ir["source_artifact"] = self._ref(report_path, "lowered")
            typed_ir["readonly_globals_identity"] = {
                "count": 1,
                "names": ["crc32_table"],
                "sha256": hashlib.sha256(
                    json.dumps(report_candidate["readonly_globals"], sort_keys=True).encode("utf-8")
                ).hexdigest(),
            }
            route = {
                "source_artifacts": {"clang_lowering_report": self._ref(report_path, "lowered")},
                "candidate_generation": {"typed_ir": typed_ir},
            }

            missing_source_sha = json.loads(json.dumps(route))
            missing_source_sha["candidate_generation"]["typed_ir"]["source_artifact"].pop("sha256")
            with self.assertRaises(SystemExit) as raised:
                module.validate_typed_ir_candidate_binding(
                    evidence_dir,
                    prefix,
                    missing_source_sha,
                    {"candidate_generation": missing_source_sha["candidate_generation"]},
                )
            self.assertIn("source_artifact", str(raised.exception))
            self.assertIn("sha256", str(raised.exception))

            profile_only = {"candidate_generation": route["candidate_generation"]}
            with self.assertRaises(SystemExit) as raised:
                module.validate_typed_ir_candidate_binding(evidence_dir, prefix, {}, profile_only)
            self.assertIn("validation_profile.candidate_generation", str(raised.exception))

            self._write_json(report_path, {"status": "lowered"})
            non_generated = {
                "source_artifacts": {"clang_lowering_report": self._ref(report_path, "lowered")},
                "candidate_generation": {
                    "typed_ir": {
                        "status": "missing",
                        "source_artifact": self._ref(report_path, "lowered"),
                        "candidate_route": None,
                        "readonly_globals": [],
                        "readonly_globals_identity": {
                            "count": 0,
                            "names": [],
                            "sha256": hashlib.sha256(json.dumps([], sort_keys=True).encode("utf-8")).hexdigest(),
                        },
                        "rust_draft_generated": False,
                        "semantic_pass": False,
                    }
                },
            }
            non_generated["source_artifacts"]["clang_lowering_report"]["sha256"] = "stale-report-sha"
            with self.assertRaises(SystemExit) as raised:
                module.validate_typed_ir_candidate_binding(
                    evidence_dir,
                    prefix,
                    non_generated,
                    {"candidate_generation": non_generated["candidate_generation"]},
                )
            self.assertIn("clang_lowering_report", str(raised.exception))

    def test_rejects_candidate_selection_id_outside_candidate_set(self) -> None:
        module = load_validator_module()
        candidate_generation = self._candidate_selection_record()
        route = {"candidate_generation": candidate_generation}
        profile = {"candidate_generation": candidate_generation}

        module.validate_typed_ir_candidate_binding(Path("unused"), "unused", route, profile)

        drifted = json.loads(json.dumps(route))
        drifted["candidate_generation"]["selected_candidate_id"] = "typed-ir:missing"
        with self.assertRaises(SystemExit) as raised:
            module.validate_typed_ir_candidate_binding(
                Path("unused"),
                "unused",
                drifted,
                {"candidate_generation": drifted["candidate_generation"]},
            )
        self.assertIn("selected_candidate_id", str(raised.exception))

    def test_rejects_p0_route_governance_missing_summary(self) -> None:
        module = load_validator_module()
        candidate_generation = self._candidate_selection_record()
        candidate_generation["selection_policy"]["stage"] = "p0_route_governance"
        route = {"candidate_generation": candidate_generation}
        profile = {"candidate_generation": candidate_generation}

        with self.assertRaises(SystemExit) as raised:
            module.validate_typed_ir_candidate_binding(Path("unused"), "unused", route, profile)

        self.assertIn("governance_summary", str(raised.exception))

        missing_set = self._candidate_selection_record()
        missing_set["selection_policy"]["stage"] = "p0_route_governance"
        missing_set.pop("candidate_set")
        with self.assertRaises(SystemExit) as raised:
            module.validate_typed_ir_candidate_binding(
                Path("unused"),
                "unused",
                {"candidate_generation": missing_set},
                {"candidate_generation": missing_set},
            )
        self.assertIn("governance_summary", str(raised.exception))

    def test_rejects_legacy_string_translator_as_selected_primary_candidate(self) -> None:
        module = load_validator_module()
        c2rust_candidate = {
            "candidate_id": "c2rust-baseline",
            "kind": "c2rust-baseline",
            "status": "skipped",
            "role": "baseline_or_repair_candidate_context",
            "correctness_role": "candidate_context_only",
            "reason": "blocked_by_missing_tools",
            "semantic_pass": False,
        }
        legacy_primary = {
            "selection_policy": {
                "stage": "post_generation_provenance",
                "selection_basis": "translator_artifact_primary_candidate",
                "semantic_acceptance": False,
                "full_router": False,
            },
            "selected_candidate_id": "primary:legacy-string-translator",
            "candidate_set": [
                {
                    "candidate_id": "primary:legacy-string-translator",
                    "kind": "legacy-string-translator",
                    "status": "generated",
                    "role": "primary_rust_draft",
                    "semantic_pass": False,
                },
                {
                    "candidate_id": "typed-ir:clang-lowered",
                    "kind": "typed-ir",
                    "status": "missing",
                    "role": "typed_ir_candidate_signal",
                    "rust_draft_generated": False,
                    "semantic_pass": False,
                },
                c2rust_candidate,
            ],
            "c2rust_baseline": c2rust_candidate,
        }

        with self.assertRaises(SystemExit) as raised:
            module.validate_typed_ir_candidate_binding(
                Path("unused"),
                "unused",
                {"candidate_generation": legacy_primary},
                {"candidate_generation": legacy_primary},
            )

        self.assertIn("legacy-string-translator", str(raised.exception))

    def test_rejects_legacy_string_translator_in_primary_candidate_field(self) -> None:
        module = load_validator_module()
        candidate_generation = self._candidate_selection_record()
        candidate_generation["selected_candidate_id"] = None
        candidate_generation["primary_candidate"] = {
            "candidate_id": "primary:legacy-string-translator",
            "selected": "legacy-string-translator",
            "fallback": True,
            "semantic_pass": False,
            "fallback_from": "clang-lowered-typed-ir",
            "fallback_reason": "clang_lowered_typed_ir_unavailable",
        }
        candidate_generation["candidate_set"][0] = {
            "candidate_id": "compat:legacy-string-translator",
            "kind": "legacy-string-translator",
            "status": "generated",
            "role": "compatibility_rust_draft",
            "semantic_pass": False,
            "correctness_role": "compatibility_only",
            "compatibility_only": True,
        }
        route = {"candidate_generation": candidate_generation}

        with self.assertRaises(SystemExit) as raised:
            module.validate_typed_ir_candidate_binding(
                Path("unused"),
                "unused",
                route,
                {"candidate_generation": candidate_generation},
            )

        self.assertIn("primary_candidate", str(raised.exception))
