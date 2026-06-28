import json
import hashlib
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"
VALIDATOR = REPO_ROOT / "validation" / "tools" / "validate_auto_translation_evidence.py"


def load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_auto_translation_evidence_under_test", VALIDATOR)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load validate_auto_translation_evidence module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ValidateAutoTranslationEvidenceTests(unittest.TestCase):
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            final_path = evidence_dir / "l3-adler32-step-final-verification.json"
            final = json.loads(final_path.read_text(encoding="utf-8"))
            final.pop("validation_profile", None)
            final_path.write_text(json.dumps(final), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            manifest_path = evidence_dir / "l3-adler32-step-evidence-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["evidence"].pop("c2rust_baseline", None)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            manifest_path = evidence_dir / "l3-adler32-step-evidence-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["evidence"]["route_decision"]["sha256"] = "wrong-sha"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            route_path = evidence_dir / "l3-adler32-step-route-decision.json"
            route = json.loads(route_path.read_text(encoding="utf-8"))
            route["source_artifacts"]["translation_plan"]["sha256"] = "stale-plan-sha"
            route_path.write_text(json.dumps(route), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
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

    def test_rejects_c2rust_candidate_claiming_semantic_pass(self) -> None:
        module = load_validator_module()
        route = {"candidate_generation": self._candidate_selection_record()}

        semantic_claim = json.loads(json.dumps(route))
        semantic_claim["candidate_generation"]["candidate_set"][2]["semantic_pass"] = True
        semantic_claim["candidate_generation"]["c2rust_baseline"]["semantic_pass"] = True
        with self.assertRaises(SystemExit) as raised:
            module.validate_typed_ir_candidate_binding(
                Path("unused"),
                "unused",
                semantic_claim,
                {"candidate_generation": semantic_claim["candidate_generation"]},
            )
        self.assertIn("semantic_pass", str(raised.exception))

        role_claim = json.loads(json.dumps(route))
        role_claim["candidate_generation"]["candidate_set"][2]["correctness_role"] = "semantic_source"
        role_claim["candidate_generation"]["c2rust_baseline"]["correctness_role"] = "semantic_source"
        with self.assertRaises(SystemExit) as raised:
            module.validate_typed_ir_candidate_binding(
                Path("unused"),
                "unused",
                role_claim,
                {"candidate_generation": role_claim["candidate_generation"]},
            )
        self.assertIn("correctness_role", str(raised.exception))

    def test_rejects_c2rust_candidate_status_reason_drift_from_baseline_manifest(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-c2rust-binding"
            baseline_path = evidence_dir / f"{prefix}-c2rust-baseline-manifest.json"
            baseline = {
                "schema_version": 1,
                "status": "skipped",
                "reason": "blocked_by_missing_tools",
                "correctness_role": "candidate_context_only",
                "output": None,
            }
            self._write_json(baseline_path, baseline)

            candidate_generation = self._candidate_selection_record()
            c2rust_candidate = candidate_generation["candidate_set"][2]
            c2rust_candidate["baseline_manifest"] = self._ref(baseline_path, "skipped")
            c2rust_candidate["output_ref"] = None
            candidate_generation["c2rust_baseline"] = c2rust_candidate

            drifted = json.loads(json.dumps(candidate_generation))
            drifted["candidate_set"][2]["status"] = "blocked"
            drifted["candidate_set"][2]["reason"] = "baseline_generation_not_enabled"
            drifted["c2rust_baseline"] = drifted["candidate_set"][2]

            with self.assertRaises(SystemExit) as raised:
                module.validate_typed_ir_candidate_binding(
                    evidence_dir,
                    prefix,
                    {"candidate_generation": drifted},
                    {"candidate_generation": drifted},
                )
            self.assertIn("c2rust_baseline status drift", str(raised.exception))

    def test_rejects_c2rust_generated_output_ref_drift_from_baseline_manifest(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-c2rust-output"
            output_path = evidence_dir / "c2rust-output.rs"
            output_path.write_text("pub unsafe fn generated() {}\n", encoding="utf-8")
            baseline_path = evidence_dir / f"{prefix}-c2rust-baseline-manifest.json"
            baseline = {
                "schema_version": 1,
                "status": "generated",
                "reason": "generated_by_c2rust",
                "correctness_role": "candidate_context_only",
                "output": {
                    "path": output_path.as_posix(),
                    "sha256": self._sha256(output_path),
                },
            }
            self._write_json(baseline_path, baseline)

            candidate_generation = self._candidate_selection_record()
            c2rust_candidate = candidate_generation["candidate_set"][2]
            c2rust_candidate["status"] = "generated"
            c2rust_candidate["reason"] = "generated_by_c2rust"
            c2rust_candidate["baseline_manifest"] = self._ref(baseline_path, "generated")
            c2rust_candidate["output_ref"] = None
            candidate_generation["c2rust_baseline"] = c2rust_candidate

            with self.assertRaises(SystemExit) as raised:
                module.validate_typed_ir_candidate_binding(
                    evidence_dir,
                    prefix,
                    {"candidate_generation": candidate_generation},
                    {"candidate_generation": candidate_generation},
                )
            self.assertIn("c2rust_baseline output_ref drift", str(raised.exception))

    def test_rejects_cache_missing_route_baseline_profile_identities(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            cache_path = evidence_dir / "l3-adler32-step-auto-cache-metadata.json"
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            cache.pop("route_decision_identity", None)
            cache_path.write_text(json.dumps(cache), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
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
            self.assertIn("route_decision_identity", result.stderr + result.stdout)

    def test_rejects_cache_missing_competition_environment_identity_when_profile_binds_it(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            profile = json.loads(
                (evidence_dir / "l3-adler32-step-validation-profile.json").read_text(encoding="utf-8")
            )
            self.assertIn("competition_environment", profile)

            cache_path = evidence_dir / "l3-adler32-step-auto-cache-metadata.json"
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            cache.pop("competition_environment_identity", None)
            cache["cache_input_fields"] = [
                field for field in cache.get("cache_input_fields", []) if field != "competition_environment_identity"
            ]
            cache_path.write_text(json.dumps(cache), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
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
            self.assertIn("competition_environment_identity", result.stderr + result.stdout)

    def test_rejects_cache_route_baseline_profile_identity_sha_drift(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            cache_path = evidence_dir / "l3-adler32-step-auto-cache-metadata.json"
            original_cache = json.loads(cache_path.read_text(encoding="utf-8"))
            for key in [
                "c2rust_baseline_identity",
                "route_decision_identity",
                "validation_profile_identity",
            ]:
                with self.subTest(key=key):
                    cache = json.loads(json.dumps(original_cache))
                    cache[key]["sha256"] = f"stale-{key}"
                    cache_path.write_text(json.dumps(cache), encoding="utf-8")

                    result = subprocess.run(
                        [
                            "python",
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
                    self.assertIn(key, result.stderr + result.stdout)

    def test_rejects_generated_c2rust_baseline_without_output(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            baseline_path = evidence_dir / "l3-adler32-step-c2rust-baseline-manifest.json"
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            baseline["status"] = "generated"
            baseline["reason"] = "test-forged-generated-status"
            baseline["selected_command"] = {
                "name": "c2rust",
                "path": "fake-c2rust",
                "available": True,
                "version_status": "OK",
                "version": "fake",
            }
            baseline["output"] = None
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
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
            self.assertIn("object", result.stderr + result.stdout)

    def test_rejects_l4_refused_route_with_generated_candidate_manifest(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            prefix = "l3-adler32-step"
            route_path = evidence_dir / f"{prefix}-route-decision.json"
            profile_path = evidence_dir / f"{prefix}-validation-profile.json"

            route = json.loads(route_path.read_text(encoding="utf-8"))
            route["level"] = "L4"
            route["status"] = "refused"
            route["translator"] = {"kind": "refuse", "candidate_generation_allowed": False}
            route["verification_profile"] = "L4-dev"
            self._write_json(route_path, route)

            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["status"] = "blocked"
            profile["profile"] = "L4-dev"
            profile["route_level"] = "L4"
            profile["skipped_gates"] = [{"gate": "candidate_generation", "reason": "route_refused"}]
            self._write_json(profile_path, profile)

            route_ref = self._ref(route_path, "refused")
            route_ref["level"] = "L4"
            profile_ref = self._ref(profile_path, "blocked")
            profile_ref["profile"] = "L4-dev"

            for file_name in [
                f"{prefix}-auto-translation-manifest.json",
                f"{prefix}-evidence-manifest.json",
                f"{prefix}-final-verification.json",
            ]:
                path = evidence_dir / file_name
                payload = json.loads(path.read_text(encoding="utf-8"))
                if file_name.endswith("evidence-manifest.json"):
                    payload["evidence"]["route_decision"] = route_ref
                    payload["evidence"]["validation_profile"] = profile_ref
                else:
                    payload["route_decision"] = route_ref
                    payload["validation_profile"] = profile_ref
                self._write_json(path, payload)

            cache_path = evidence_dir / f"{prefix}-auto-cache-metadata.json"
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            cache["route_decision_identity"] = {"status": "refused", "sha256": self._sha256_json(route)}
            cache["validation_profile_identity"] = {"status": "blocked", "sha256": self._sha256_json(profile)}
            cache["dependent_artifacts"]["route_decision"] = route_ref
            cache["dependent_artifacts"]["validation_profile"] = profile_ref
            self._write_json(cache_path, cache)

            result = subprocess.run(
                [
                    "python",
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
            self.assertIn(
                "L4/refused route cannot have generated candidate evidence",
                result.stderr + result.stdout,
            )

    def test_rejects_l4_refused_route_with_nested_candidate_artifacts(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            prefix = "l3-adler32-step"
            route_path = evidence_dir / f"{prefix}-route-decision.json"
            profile_path = evidence_dir / f"{prefix}-validation-profile.json"

            route = json.loads(route_path.read_text(encoding="utf-8"))
            route["level"] = "L4"
            route["status"] = "refused"
            route["translator"] = {"kind": "refuse", "candidate_generation_allowed": False}
            route["verification_profile"] = "L4-dev"
            self._write_json(route_path, route)

            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["status"] = "blocked"
            profile["profile"] = "L4-dev"
            profile["route_level"] = "L4"
            profile["skipped_gates"] = [{"gate": "candidate_generation", "reason": "route_refused"}]
            self._write_json(profile_path, profile)

            route_ref = self._ref(route_path, "refused")
            route_ref["level"] = "L4"
            profile_ref = self._ref(profile_path, "blocked")
            profile_ref["profile"] = "L4-dev"

            for file_name in [
                f"{prefix}-auto-translation-manifest.json",
                f"{prefix}-evidence-manifest.json",
                f"{prefix}-final-verification.json",
            ]:
                path = evidence_dir / file_name
                payload = json.loads(path.read_text(encoding="utf-8"))
                if file_name.endswith("evidence-manifest.json"):
                    payload["evidence"]["route_decision"] = route_ref
                    payload["evidence"]["validation_profile"] = profile_ref
                else:
                    payload["route_decision"] = route_ref
                    payload["validation_profile"] = profile_ref
                if file_name.endswith("auto-translation-manifest.json"):
                    payload["status"] = "candidate_refused"
                self._write_json(path, payload)

            cache_path = evidence_dir / f"{prefix}-auto-cache-metadata.json"
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            cache["route_decision_identity"] = {"status": "refused", "sha256": self._sha256_json(route)}
            cache["validation_profile_identity"] = {"status": "blocked", "sha256": self._sha256_json(profile)}
            cache["dependent_artifacts"]["route_decision"] = route_ref
            cache["dependent_artifacts"]["validation_profile"] = profile_ref
            self._write_json(cache_path, cache)

            result = subprocess.run(
                [
                    "python",
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
            self.assertIn(
                "L4/refused route cannot contain candidate artifact status",
                result.stderr + result.stdout,
            )

    def test_l4_refused_status_scanner_rejects_draft_and_accepted_artifact_statuses(self) -> None:
        validator = load_validator_module()

        paths = validator.candidate_status_paths(
            {
                "generated_artifacts": [
                    {"status": "draft_generated"},
                    {"status": "accepted_after_gates"},
                    {"status": "accepted_evidence_bound"},
                ]
            }
        )

        self.assertIn("$.generated_artifacts[0].status", paths)
        self.assertIn("$.generated_artifacts[1].status", paths)
        self.assertIn("$.generated_artifacts[2].status", paths)

    def test_l4_refused_repair_playbook_rejects_missing_required_fields(self) -> None:
        validator = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            blocked_path = evidence_dir / "l3-demo-self-healing-blocked-repairs.json"
            blocked_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "target_id": "demo",
                        "slice_id": "demo",
                        "status": "recorded",
                        "blocked_repairs": [
                            {
                                "repair_id": "repair-route-refused-1",
                                "blocked_reason": "route refused",
                                "forbidden_change": "unsupported_control_flow",
                                "candidate_patch_id": "patch-route-refused-1",
                                "source_span": {"file": "candidate.rs", "line_start": 1, "line_end": 1},
                                "human_action_required": True,
                            }
                        ],
                        "cache_invalidation_keys": ["source_commit=1234567"],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit) as raised:
                validator.validate_l4_refused_repair_playbook(evidence_dir, "l3-demo")

            self.assertIn("repair playbook", str(raised.exception))

    def test_l4_refused_repair_playbook_accepts_minimal_required_fields(self) -> None:
        validator = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            blocked_path = evidence_dir / "l3-demo-self-healing-blocked-repairs.json"
            blocked_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "target_id": "demo",
                        "slice_id": "demo",
                        "status": "recorded",
                        "blocked_repairs": [
                            {
                                "repair_id": "repair-route-refused-1",
                                "blocked_reason": "route refused",
                                "forbidden_change": "unsupported_control_flow",
                                "candidate_patch_id": "patch-route-refused-1",
                                "source_span": {"file": "candidate.rs", "line_start": 1, "line_end": 1},
                                "human_action_required": True,
                                "ir_feature_gap": {"kind": "unsupported_lvalue"},
                                "oracle_fixture_gap": {"status": "not_blocking"},
                                "candidate_routes": [
                                    {"route": "typed_ir"},
                                    {"route": "c2rust"},
                                    {"route": "llm"},
                                    {"route": "manual"},
                                ],
                                "smallest_next_test": {"kind": "route_refusal_regression"},
                                "human_intervention_point": "extend typed IR support",
                            }
                        ],
                        "cache_invalidation_keys": ["source_commit=1234567"],
                    }
                ),
                encoding="utf-8",
            )

            validator.validate_l4_refused_repair_playbook(evidence_dir, "l3-demo")

    def test_rejects_toolchain_generated_spoof_without_generated_oracle_status(self) -> None:
        validator = load_validator_module()

        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            oracle = {
                "status": "DRAFT_GENERATED",
                "toolchain_status": "C_ORACLE_GENERATED",
                "semantic_pass": True,
            }

            with self.assertRaises(SystemExit) as raised:
                validator.validate_draft_oracle_fail_closed(
                    evidence_dir,
                    "l3-spoof",
                    oracle,
                    evidence_dir / "l3-spoof-c-oracle-status.json",
                )

            self.assertIn("draft oracle", str(raised.exception))

    def test_rejects_global_dependency_without_type_map_or_oracle_linkage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            evidence_dir = out_root / "demo" / "auto-translation" / "global-dependency-validator"
            type_map_path = evidence_dir / "l3-global-dependency-validator-type-map.json"
            type_map = json.loads(type_map_path.read_text(encoding="utf-8"))
            type_map.pop("global_dependencies", None)
            self._write_json(type_map_path, type_map)
            self._refresh_route_source_artifact_ref(
                evidence_dir,
                "global-dependency-validator",
                "type_map",
                type_map_path,
                type_map.get("status", "recorded"),
            )

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("global dependency", result.stderr + result.stdout)

            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            oracle_path = evidence_dir / "l3-global-dependency-validator-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            oracle.pop("global_linkage_requirements", None)
            self._write_json(oracle_path, oracle)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("global dependency", result.stderr + result.stdout)

    def test_rejects_global_dependency_metadata_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            type_map_path = evidence_dir / "l3-global-dependency-validator-type-map.json"
            type_map = json.loads(type_map_path.read_text(encoding="utf-8"))
            type_map["global_dependencies"][0]["sha256"] = "stale-table-sha"
            type_map["global_dependencies"][0]["source_span"]["line_start"] = 99
            self._write_json(type_map_path, type_map)
            self._refresh_route_source_artifact_ref(
                evidence_dir,
                "global-dependency-validator",
                "type_map",
                type_map_path,
                type_map.get("status", "recorded"),
            )

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("global dependency", result.stderr + result.stdout)

    def test_rejects_extra_stale_global_dependency(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            type_map_path = evidence_dir / "l3-global-dependency-validator-type-map.json"
            type_map = json.loads(type_map_path.read_text(encoding="utf-8"))
            stale = dict(type_map["global_dependencies"][0])
            stale["name"] = "stale_table"
            stale["sha256"] = "stale-sha"
            type_map["global_dependencies"].append(stale)
            self._write_json(type_map_path, type_map)
            self._refresh_route_source_artifact_ref(
                evidence_dir,
                "global-dependency-validator",
                "type_map",
                type_map_path,
                type_map.get("status", "recorded"),
            )

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("global dependency", result.stderr + result.stdout)

    def test_rejects_stale_global_dependency_when_slice_spec_has_no_globals(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            spec = self._global_dependency_spec()
            spec["c_boundary"]["direct_dependencies"] = []
            spec_path = tmp_path / "global-dependency-validator.json"
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

            evidence_dir = out_root / "demo" / "auto-translation" / "global-dependency-validator"
            cache_path = evidence_dir / "l3-global-dependency-validator-auto-cache-metadata.json"
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            cache["global_dependency_identity"] = {
                "sha256": "stale-global-identity",
                "count": 1,
                "names": ["stale_table"],
            }
            self._write_json(cache_path, cache)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("unexpected global dependency identity", result.stderr + result.stdout)

    def test_rejects_global_dependency_cache_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            cache_path = evidence_dir / "l3-global-dependency-validator-auto-cache-metadata.json"
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            cache["global_dependency_identity"]["count"] = 0
            cache["global_dependency_identity"]["sha256"] = "stale-global-identity"
            self._write_json(cache_path, cache)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("global dependency", result.stderr + result.stdout)

    def test_rejects_oracle_status_missing_harness_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            oracle_path = evidence_dir / "l3-global-dependency-validator-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            oracle.pop("harness_contract", None)
            self._write_json(oracle_path, oracle)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("harness contract", result.stderr + result.stdout)

    def test_rejects_oracle_harness_contract_global_dependency_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            oracle_path = evidence_dir / "l3-global-dependency-validator-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            oracle["harness_contract"]["global_dependencies"][0]["sha256"] = "stale-table-sha"
            self._write_json(oracle_path, oracle)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("harness contract", result.stderr + result.stdout)

    def test_rejects_oracle_fixture_binding_case_output_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            oracle_path = evidence_dir / "l3-global-dependency-validator-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            oracle["fixture_binding"] = {
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
                        "expected_outputs": {"value": 99},
                        "observable_outputs": ["value"],
                        "missing_observable_outputs": [],
                        "binding_status": "declared_not_executed",
                    }
                ],
                "expected_output_status": "declared_not_executed",
            }
            self._write_json(oracle_path, oracle)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("fixture", result.stderr + result.stdout)

    def test_rejects_oracle_harness_contract_fixture_case_output_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            oracle_path = evidence_dir / "l3-global-dependency-validator-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            oracle["harness_contract"]["fixture"] = {
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
                        "expected_outputs": {"value": 99},
                        "observable_outputs": ["value"],
                        "missing_observable_outputs": [],
                        "binding_status": "declared_not_executed",
                    }
                ],
                "expected_output_status": "declared_not_executed",
            }
            self._write_json(oracle_path, oracle)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("fixture", result.stderr + result.stdout)

    def test_rejects_oracle_harness_draft_ref_sha_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            oracle_path = evidence_dir / "l3-global-dependency-validator-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            oracle["harness_draft_ref"]["sha256"] = "stale-harness-sha"
            self._write_json(oracle_path, oracle)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("harness draft", result.stderr + result.stdout)

    def test_rejects_oracle_compile_command_include_path_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            oracle_path = evidence_dir / "l3-global-dependency-validator-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            oracle["compile_command_draft"]["resolved_include_paths"] = ["inc"]
            oracle["compile_command_draft"]["argv"] = [
                item.replace("-Iunit/inc", "-Iinc")
                if isinstance(item, str)
                else item
                for item in oracle["compile_command_draft"]["argv"]
            ]
            self._write_json(oracle_path, oracle)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("compile command", result.stderr + result.stdout)

    def test_rejects_oracle_compile_execution_argv_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            oracle_path = evidence_dir / "l3-global-dependency-validator-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            oracle["compile_execution"] = {
                "status": "skipped_by_flag",
                "attempted": False,
                "argv": ["cc", "stale.c"],
                "working_directory": str(evidence_dir).replace("\\", "/"),
                "toolchain_status_after_attempt": "DRAFT_NOT_EXECUTED",
                "semantic_pass": False,
                "diagnostics": ["C oracle compile execution skipped by --skip-c-oracle."],
            }
            self._write_json(oracle_path, oracle)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("compile execution", result.stderr + result.stdout)

    def test_rejects_compile_execution_skipped_spoofing_generated_toolchain(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            oracle_path = evidence_dir / "l3-global-dependency-validator-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            oracle["toolchain_status"] = "C_ORACLE_GENERATED"
            oracle["semantic_pass"] = True
            oracle["compile_execution"]["toolchain_status_after_attempt"] = "C_ORACLE_GENERATED"
            self._write_json(oracle_path, oracle)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("compile execution", result.stderr + result.stdout)

    def test_rejects_wsl_compile_execution_missing_execution_argv(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            oracle_path = evidence_dir / "l3-global-dependency-validator-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            oracle["toolchain_status"] = "COMPILE_FAILED"
            oracle["semantic_pass"] = False
            oracle["compile_execution"] = {
                "status": "compile_failed",
                "attempted": True,
                "argv": oracle["compile_command_draft"]["argv"],
                "working_directory": str(evidence_dir).replace("\\", "/"),
                "toolchain_status_after_attempt": "COMPILE_FAILED",
                "semantic_pass": False,
                "compiler_path": "/usr/bin/cc",
                "toolchain_adapter": "wsl",
                "returncode": 1,
                "stdout": "",
                "stderr": "compile failed",
                "diagnostics": ["C oracle compile command failed; no oracle evidence accepted."],
            }
            self._write_json(oracle_path, oracle)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("toolchain provenance", result.stderr + result.stdout)

    def test_rejects_wsl_compile_execution_launcher_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            oracle_path = evidence_dir / "l3-global-dependency-validator-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            oracle["toolchain_status"] = "COMPILE_FAILED"
            oracle["semantic_pass"] = False
            oracle["compile_execution"] = {
                "status": "compile_failed",
                "attempted": True,
                "argv": oracle["compile_command_draft"]["argv"],
                "working_directory": str(evidence_dir).replace("\\", "/"),
                "toolchain_status_after_attempt": "COMPILE_FAILED",
                "semantic_pass": False,
                "compiler_path": "/usr/bin/cc",
                "toolchain_adapter": "wsl",
                "execution_argv": [
                    "not-wsl.exe",
                    "-e",
                    "sh",
                    "-lc",
                    "cd /tmp && /usr/bin/cc harness.c -o harness.exe",
                ],
                "returncode": 1,
                "stdout": "",
                "stderr": "compile failed",
                "diagnostics": ["C oracle compile command failed; no oracle evidence accepted."],
            }
            self._write_json(oracle_path, oracle)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("toolchain provenance", result.stderr + result.stdout)

    def test_rejects_harness_execution_semantic_pass_spoofing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            oracle_path = evidence_dir / "l3-global-dependency-validator-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            executable_path = (
                evidence_dir / "l3-global-dependency-validator-c-oracle-harness-draft.exe"
            ).as_posix()
            oracle["toolchain_status"] = "COMPILE_SUCCEEDED_NOT_ORACLE"
            oracle["semantic_pass"] = False
            oracle["compile_execution"] = {
                "status": "compile_succeeded_not_oracle",
                "attempted": True,
                "argv": oracle["compile_command_draft"]["argv"],
                "working_directory": str(evidence_dir).replace("\\", "/"),
                "toolchain_status_after_attempt": "COMPILE_SUCCEEDED_NOT_ORACLE",
                "semantic_pass": False,
                "compiler_path": "unit/cc",
                "returncode": 0,
                "stdout": "",
                "stderr": "",
                "diagnostics": [
                    "C oracle compile command succeeded, but execution/diff gates are still required."
                ],
                "harness_execution": {
                    "status": "exited_zero_not_oracle",
                    "attempted": True,
                    "argv": [executable_path],
                    "working_directory": str(evidence_dir).replace("\\", "/"),
                    "executable_path": executable_path,
                    "timeout_seconds": 30,
                    "semantic_pass": True,
                    "returncode": 0,
                    "stdout": "",
                    "stderr": "",
                    "diagnostics": [
                        "C oracle harness executed, but execution output has not passed oracle diff gates."
                    ],
                },
            }
            self._write_json(oracle_path, oracle)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("harness execution", result.stderr + result.stdout)

    def test_rejects_harness_execution_missing_output_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            oracle_path = evidence_dir / "l3-global-dependency-validator-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            executable_path = (
                evidence_dir / "l3-global-dependency-validator-c-oracle-harness-draft.exe"
            ).as_posix()
            oracle["toolchain_status"] = "COMPILE_SUCCEEDED_NOT_ORACLE"
            oracle["semantic_pass"] = False
            oracle["compile_execution"] = {
                "status": "compile_succeeded_not_oracle",
                "attempted": True,
                "argv": oracle["compile_command_draft"]["argv"],
                "working_directory": str(evidence_dir).replace("\\", "/"),
                "toolchain_status_after_attempt": "COMPILE_SUCCEEDED_NOT_ORACLE",
                "semantic_pass": False,
                "compiler_path": "unit/cc",
                "returncode": 0,
                "stdout": "",
                "stderr": "",
                "diagnostics": [
                    "C oracle compile command succeeded, but execution/diff gates are still required."
                ],
                "harness_execution": {
                    "status": "exited_zero_not_oracle",
                    "attempted": True,
                    "argv": [executable_path],
                    "working_directory": str(evidence_dir).replace("\\", "/"),
                    "executable_path": executable_path,
                    "timeout_seconds": 30,
                    "semantic_pass": False,
                    "returncode": 0,
                    "stdout": "fixture case case-one value matched\n",
                    "stderr": "",
                    "diagnostics": [
                        "C oracle harness executed, but execution output has not passed oracle diff gates."
                    ],
                },
            }
            self._write_json(oracle_path, oracle)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("harness output gate", result.stderr + result.stdout)

    def test_rejects_compile_success_missing_harness_execution(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            oracle_path = evidence_dir / "l3-global-dependency-validator-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            oracle["toolchain_status"] = "COMPILE_SUCCEEDED_NOT_ORACLE"
            oracle["semantic_pass"] = False
            oracle["compile_execution"] = {
                "status": "compile_succeeded_not_oracle",
                "attempted": True,
                "argv": oracle["compile_command_draft"]["argv"],
                "working_directory": str(evidence_dir).replace("\\", "/"),
                "toolchain_status_after_attempt": "COMPILE_SUCCEEDED_NOT_ORACLE",
                "semantic_pass": False,
                "compiler_path": "unit/cc",
                "returncode": 0,
                "stdout": "",
                "stderr": "",
                "diagnostics": [
                    "C oracle compile command succeeded, but execution/diff gates are still required."
                ],
            }
            self._write_json(oracle_path, oracle)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("harness execution", result.stderr + result.stdout)

    def test_rejects_schema_diff_missing_draft_blockers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            diff_path = evidence_dir / "l3-global-dependency-validator-diff.json"
            diff = json.loads(diff_path.read_text(encoding="utf-8"))
            diff.pop("blocked_by", None)
            self._write_json(diff_path, diff)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("schema diff", result.stderr + result.stdout)
            self.assertIn("blocked_by", result.stderr + result.stdout)

    def test_rejects_negative_diff_missing_draft_requirements(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            negative_path = evidence_dir / "l3-global-dependency-validator-negative-diff.json"
            negative = json.loads(negative_path.read_text(encoding="utf-8"))
            negative.pop("required_inputs", None)
            self._write_json(negative_path, negative)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("negative diff", result.stderr + result.stdout)
            self.assertIn("required_inputs", result.stderr + result.stdout)

    def test_rejects_harness_output_gate_semantic_pass_spoofing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            oracle_path = evidence_dir / "l3-global-dependency-validator-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            executable_path = (
                evidence_dir / "l3-global-dependency-validator-c-oracle-harness-draft.exe"
            ).as_posix()
            oracle["toolchain_status"] = "COMPILE_SUCCEEDED_NOT_ORACLE"
            oracle["semantic_pass"] = False
            oracle["compile_execution"] = {
                "status": "compile_succeeded_not_oracle",
                "attempted": True,
                "argv": oracle["compile_command_draft"]["argv"],
                "working_directory": str(evidence_dir).replace("\\", "/"),
                "toolchain_status_after_attempt": "COMPILE_SUCCEEDED_NOT_ORACLE",
                "semantic_pass": False,
                "compiler_path": "unit/cc",
                "returncode": 0,
                "stdout": "",
                "stderr": "",
                "diagnostics": [
                    "C oracle compile command succeeded, but execution/diff gates are still required."
                ],
                "harness_execution": {
                    "status": "exited_zero_not_oracle",
                    "attempted": True,
                    "argv": [executable_path],
                    "working_directory": str(evidence_dir).replace("\\", "/"),
                    "executable_path": executable_path,
                    "timeout_seconds": 30,
                    "semantic_pass": False,
                    "returncode": 0,
                    "stdout": "fixture case case-one value matched\n",
                    "stderr": "",
                    "output_gate": {
                        "status": "matched_not_oracle",
                        "semantic_pass": True,
                        "expected_stdout_fragments": ["fixture case case-one value matched"],
                        "matched_stdout_fragments": ["fixture case case-one value matched"],
                        "missing_stdout_fragments": [],
                        "diagnostics": [
                            "C oracle harness stdout matched draft fixture markers, but oracle diff gates are still required."
                        ],
                    },
                    "diagnostics": [
                        "C oracle harness executed, but execution output has not passed oracle diff gates."
                    ],
                },
            }
            self._write_json(oracle_path, oracle)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("harness output gate", result.stderr + result.stdout)

    def test_rejects_oracle_compile_command_source_linkage_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            oracle_path = evidence_dir / "l3-global-dependency-validator-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            oracle["compile_command_draft"]["link_source_files"][0]["resolved_path"] = "global.c"
            oracle["compile_command_draft"]["argv"].remove("unit/global.c")
            oracle["compile_command_draft"]["argv"].insert(-2, "global.c")
            self._write_json(oracle_path, oracle)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("compile command", result.stderr + result.stdout)

    def test_rejects_cache_oracle_harness_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            cache_path = evidence_dir / "l3-global-dependency-validator-auto-cache-metadata.json"
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            cache["c_oracle_harness_identity"]["sha256"] = "stale-harness-sha"
            self._write_json(cache_path, cache)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("oracle harness identity", result.stderr + result.stdout)

    def test_rejects_oracle_harness_missing_function_prototype(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            harness_path = evidence_dir / "l3-global-dependency-validator-c-oracle-harness-draft.c"
            harness = harness_path.read_text(encoding="utf-8")
            harness = harness.replace("int global_dependency_validator(int value);\n\n", "")
            harness_path.write_text(harness, encoding="utf-8")
            harness_ref = self._ref(harness_path, "draft")
            oracle_path = evidence_dir / "l3-global-dependency-validator-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            oracle["harness_draft_ref"] = harness_ref
            self._write_json(oracle_path, oracle)
            cache_path = evidence_dir / "l3-global-dependency-validator-auto-cache-metadata.json"
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            cache["c_oracle_harness_identity"] = harness_ref
            self._write_json(cache_path, cache)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("function prototype", result.stderr + result.stdout)

    def test_rejects_draft_oracle_claiming_passed_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            prefix = "l3-global-dependency-validator"
            oracle_path = evidence_dir / f"{prefix}-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            self.assertNotEqual(oracle["status"], "C_ORACLE_GENERATED")

            final_path = evidence_dir / f"{prefix}-final-verification.json"
            final = json.loads(final_path.read_text(encoding="utf-8"))
            final["status"] = "passed"
            final["semantic_pass"] = True
            self._write_json(final_path, final)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("draft oracle", result.stderr + result.stdout)

    def test_rejects_oracle_status_spoofed_without_toolchain_generation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            prefix = "l3-global-dependency-validator"
            oracle_path = evidence_dir / f"{prefix}-c-oracle-status.json"
            oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
            oracle["status"] = "C_ORACLE_GENERATED"
            oracle["semantic_pass"] = True
            oracle["toolchain_status"] = "DRAFT_NOT_EXECUTED"
            self._write_json(oracle_path, oracle)

            final_path = evidence_dir / f"{prefix}-final-verification.json"
            final = json.loads(final_path.read_text(encoding="utf-8"))
            final["status"] = "passed"
            final["semantic_pass"] = True
            self._write_json(final_path, final)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("draft oracle", result.stderr + result.stdout)

    def test_rejects_stale_slice_contract_global_dependency(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._global_dependency_evidence(Path(tmp))
            contract_path = evidence_dir / "l3-global-dependency-validator-slice-contract.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["c_boundary"]["direct_dependencies"] = []
            self._write_json(contract_path, contract)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "global-dependency-validator",
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
            self.assertIn("global dependency", result.stderr + result.stdout)

    def test_rejects_semantic_pass_missing_external_callee_context_binding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            _, out_root, _ = self._call_expression_semantic_pass_fixture(tmp_path)
            spec_path = self._write_call_expression_external_callee_spec(tmp_path)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "call-expression",
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

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("external callee", result.stderr + result.stdout)

    def test_rejects_default_validation_missing_external_callee_context_binding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            _, out_root, _ = self._call_expression_semantic_pass_fixture(tmp_path)
            spec_path = self._write_call_expression_external_callee_spec(tmp_path)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "call-expression",
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
            self.assertIn("external callee", result.stderr + result.stdout)

    def test_external_direct_callee_context_requires_every_call_site_binding(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-external-callee"
            slice_spec, plan, context = self._external_callee_context_payloads()
            context["call_edge_to_callee_binding"] = context["call_edge_to_callee_binding"][:-1]
            self._write_json(evidence_dir / f"{prefix}-auto-translation-plan.json", plan)
            self._write_json(evidence_dir / f"{prefix}-context-pack.json", context)

            with self.assertRaises(SystemExit) as raised:
                module.validate_external_direct_callee_context(
                    slice_spec,
                    evidence_dir,
                    prefix,
                    self._external_callee_manifest_scope(),
                    self._external_callee_manifest_scope(),
                )

            self.assertIn("external callee call-site binding", str(raised.exception))

    def test_external_direct_callee_context_rejects_context_direct_call_edge_drift(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-external-callee"
            slice_spec, plan, context = self._external_callee_context_payloads()
            context["direct_call_edges"][1]["statement_context"] = "assign:drifted"
            context["call_edge_to_callee_binding"][1]["statement_context"] = "assign:drifted"
            self._write_json(evidence_dir / f"{prefix}-auto-translation-plan.json", plan)
            self._write_json(evidence_dir / f"{prefix}-context-pack.json", context)

            with self.assertRaises(SystemExit) as raised:
                module.validate_external_direct_callee_context(
                    slice_spec,
                    evidence_dir,
                    prefix,
                    self._external_callee_manifest_scope(),
                    self._external_callee_manifest_scope(),
                )

            self.assertIn("translation plan and context pack direct_call_edges", str(raised.exception))

    def test_external_direct_callee_context_allows_blocked_external_callee(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-external-callee"
            slice_spec, plan, context = self._blocked_external_callee_context_payloads()
            self._write_json(evidence_dir / f"{prefix}-auto-translation-plan.json", plan)
            self._write_json(evidence_dir / f"{prefix}-context-pack.json", context)

            module.validate_external_direct_callee_context(
                slice_spec,
                evidence_dir,
                prefix,
                self._blocked_external_callee_manifest_scope(),
                self._blocked_external_callee_manifest_scope(),
            )

    def test_external_direct_callee_context_rejects_signature_shape_drift(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-external-callee"
            slice_spec, plan, context = self._external_callee_context_payloads()
            plan["translation_summary"]["external_direct_callees"][0]["return_type"] = "long"
            context["external_direct_callees"][0]["parameters"][0]["c_type"] = "long"
            self._write_json(evidence_dir / f"{prefix}-auto-translation-plan.json", plan)
            self._write_json(evidence_dir / f"{prefix}-context-pack.json", context)

            with self.assertRaises(SystemExit) as raised:
                module.validate_external_direct_callee_context(
                    slice_spec,
                    evidence_dir,
                    prefix,
                    self._external_callee_manifest_scope(),
                    self._external_callee_manifest_scope(),
                )

            self.assertIn("external callee signature shape mismatch", str(raised.exception))

    def test_external_direct_callee_context_rejects_signature_binding_drift(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-external-callee"
            slice_spec, plan, context = self._external_callee_context_payloads()
            context["signature_bindings"][0]["signature_ref"] = "sig-other"
            self._write_json(evidence_dir / f"{prefix}-auto-translation-plan.json", plan)
            self._write_json(evidence_dir / f"{prefix}-context-pack.json", context)

            with self.assertRaises(SystemExit) as raised:
                module.validate_external_direct_callee_context(
                    slice_spec,
                    evidence_dir,
                    prefix,
                    self._external_callee_manifest_scope(),
                    self._external_callee_manifest_scope(),
                )

            self.assertIn("external callee signature binding mismatch", str(raised.exception))

    def test_external_direct_callee_context_rejects_callee_source_drift(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-external-callee"
            slice_spec, plan, context = self._external_callee_context_payloads()
            context["callee_sources"][0]["sha256"] = "wrong-sha"
            self._write_json(evidence_dir / f"{prefix}-auto-translation-plan.json", plan)
            self._write_json(evidence_dir / f"{prefix}-context-pack.json", context)

            with self.assertRaises(SystemExit) as raised:
                module.validate_external_direct_callee_context(
                    slice_spec,
                    evidence_dir,
                    prefix,
                    self._external_callee_manifest_scope(),
                    self._external_callee_manifest_scope(),
                )

            self.assertIn("external callee source binding mismatch", str(raised.exception))

    def test_external_direct_callee_context_rejects_call_site_enrichment_drift(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-external-callee"
            slice_spec, plan, context = self._external_callee_context_payloads()
            plan["translation_summary"]["call_expressions"][0]["callee_scope"] = "internal"
            context["direct_call_edges"][1]["stub_status"] = "missing"
            self._write_json(evidence_dir / f"{prefix}-auto-translation-plan.json", plan)
            self._write_json(evidence_dir / f"{prefix}-context-pack.json", context)

            with self.assertRaises(SystemExit) as raised:
                module.validate_external_direct_callee_context(
                    slice_spec,
                    evidence_dir,
                    prefix,
                    self._external_callee_manifest_scope(),
                    self._external_callee_manifest_scope(),
                )

            self.assertIn("external callee call-site metadata mismatch", str(raised.exception))

    def test_semantic_pass_allows_l4_refused_route_when_accepted_evidence_binding_is_authoritative(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path, out_root, evidence_dir = self._call_expression_semantic_pass_fixture(tmp_path)
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            spec["claim_boundary"]["accepted_evidence_authoritative"] = True
            spec_path = tmp_path / "demo-call-expression-authoritative.json"
            self._write_json(spec_path, spec)
            self._promote_call_expression_fixture_to_l4_authoritative(evidence_dir)
            self._add_call_expression_oracle_boundary_contract(evidence_dir)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "call-expression",
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
                result.returncode,
                0,
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["semantic_pass"])
            self.assertIn("semantic_claim_source", payload)
            self.assertIn("generated_draft_semantic_pass", payload)
            self.assertIn("semantic_claim_source", payload["semantic"])
            self.assertIn("generated_draft_semantic_pass", payload["semantic"])
            self.assertEqual(payload["semantic_claim_source"], "accepted_evidence_binding")
            self.assertIs(payload["generated_draft_semantic_pass"], False)
            self.assertEqual(payload["semantic"]["semantic_claim_source"], "accepted_evidence_binding")
            self.assertIs(payload["semantic"]["generated_draft_semantic_pass"], False)

    def test_semantic_pass_rejects_missing_oracle_boundary_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path, out_root, evidence_dir = self._call_expression_semantic_pass_fixture(tmp_path)
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            spec["claim_boundary"]["accepted_evidence_authoritative"] = True
            spec_path = tmp_path / "demo-call-expression-authoritative.json"
            self._write_json(spec_path, spec)
            self._promote_call_expression_fixture_to_l4_authoritative(evidence_dir)
            profile_path = evidence_dir / "l3-call-expression-validation-profile.json"
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile.pop("oracle_boundary_contract", None)
            self._write_json(profile_path, profile)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "call-expression",
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

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("oracle_boundary_contract", result.stderr + result.stdout)

    def test_semantic_pass_rejects_invalid_optional_target_abi_width_contract(self) -> None:
        for key, value, expected in [
            ("char_width", 0, "target.char_width invalid"),
            ("short_width", "not-a-width", "target.short_width invalid"),
            ("long_long_width", -64, "target.long_long_width invalid"),
            ("plain_char_signed", "signed", "target.plain_char_signed invalid"),
        ]:
            with self.subTest(key=key):
                with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
                    tmp_path = Path(tmp)
                    spec_path, out_root, evidence_dir = self._call_expression_semantic_pass_fixture(
                        tmp_path
                    )
                    spec = json.loads(spec_path.read_text(encoding="utf-8"))
                    spec["claim_boundary"]["accepted_evidence_authoritative"] = True
                    spec_path = tmp_path / "demo-call-expression-authoritative.json"
                    self._write_json(spec_path, spec)
                    self._promote_call_expression_fixture_to_l4_authoritative(evidence_dir)
                    self._add_call_expression_oracle_boundary_contract(evidence_dir)

                    for artifact in [
                        evidence_dir / "l3-call-expression-validation-profile.json",
                        evidence_dir / "l3-call-expression-final-verification.json",
                    ]:
                        payload = json.loads(artifact.read_text(encoding="utf-8"))
                        payload["oracle_boundary_contract"]["target"][key] = value
                        self._write_json(artifact, payload)
                    self._refresh_call_expression_validation_profile_refs(evidence_dir)

                    result = subprocess.run(
                        [
                            "python",
                            str(VALIDATOR),
                            "--target-id",
                            "demo",
                            "--slice-id",
                            "call-expression",
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

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(expected, result.stderr + result.stdout)

    def test_semantic_pass_rejects_root_accepted_c_oracle_sha_drift(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-calc-crc32.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "evidence"
            subprocess.run(
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
                check=True,
            )

            evidence_dir = out_root / "flashdb" / "auto-translation" / "real-fdb-calc-crc32"
            prefix = "l3-real-fdb-calc-crc32"
            temp_root_oracle = out_root / "flashdb" / f"{prefix}-c-oracle.json"
            shutil.copy2(REPO_ROOT / "validation" / "evidence" / "flashdb" / f"{prefix}-c-oracle.json", temp_root_oracle)
            stale_sha = self._sha256(temp_root_oracle)

            c_oracle_status_path = evidence_dir / f"{prefix}-c-oracle-status.json"
            c_oracle_status = json.loads(c_oracle_status_path.read_text(encoding="utf-8"))
            c_oracle_status["accepted_oracle"] = {
                "path": temp_root_oracle.as_posix(),
                "sha256": stale_sha,
                "status": "passed",
            }
            self._write_json(c_oracle_status_path, c_oracle_status)
            self._bind_manifest_ref(evidence_dir, prefix, "c_oracle", c_oracle_status_path, "C_ORACLE_GENERATED")

            auto_manifest_path = evidence_dir / f"{prefix}-auto-translation-manifest.json"
            auto_manifest = json.loads(auto_manifest_path.read_text(encoding="utf-8"))
            auto_manifest["accepted_evidence_binding"]["paths"]["c_oracle"] = temp_root_oracle.as_posix()
            auto_manifest["accepted_evidence_binding"]["path_sha256"]["c_oracle"] = stale_sha
            self._write_json(auto_manifest_path, auto_manifest)

            root_oracle = json.loads(temp_root_oracle.read_text(encoding="utf-8"))
            root_oracle["cases"][0]["return_code"] = 1
            self._write_json(temp_root_oracle, root_oracle)

            result = subprocess.run(
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

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("accepted c_oracle", result.stderr + result.stdout)
            self.assertIn("sha256", result.stderr + result.stdout)

    def test_semantic_pass_rejects_l4_authoritative_artifacts_without_spec_authorization(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path, out_root, evidence_dir = self._call_expression_semantic_pass_fixture(tmp_path)
            self._promote_call_expression_fixture_to_l4_authoritative(evidence_dir)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "call-expression",
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

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("accepted_evidence_authoritative", result.stderr + result.stdout)

    def test_rejects_semantic_pass_schema_diff_missing_accepted_ref(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._call_expression_semantic_pass_fixture(Path(tmp))
            prefix = "l3-call-expression"
            diff_path = evidence_dir / f"{prefix}-diff.json"
            diff = json.loads(diff_path.read_text(encoding="utf-8"))
            diff.pop("accepted_diff", None)
            self._write_json(diff_path, diff)
            self._bind_manifest_ref(evidence_dir, prefix, "schema_diff", diff_path, "passed")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "call-expression",
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

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("schema diff", result.stderr + result.stdout)
            self.assertIn("accepted_diff", result.stderr + result.stdout)

    def test_rejects_semantic_pass_schema_diff_missing_gate_fields(self) -> None:
        for field in ["diff_gate", "accepted_diff_required", "blocked_by", "required_inputs"]:
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
                    spec_path, out_root, evidence_dir = self._call_expression_semantic_pass_fixture(Path(tmp))
                    prefix = "l3-call-expression"
                    diff_path = evidence_dir / f"{prefix}-diff.json"
                    diff = json.loads(diff_path.read_text(encoding="utf-8"))
                    diff.pop(field, None)
                    self._write_json(diff_path, diff)
                    self._bind_manifest_ref(evidence_dir, prefix, "schema_diff", diff_path, "passed")

                    result = subprocess.run(
                        [
                            "python",
                            str(VALIDATOR),
                            "--target-id",
                            "demo",
                            "--slice-id",
                            "call-expression",
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

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("schema diff", result.stderr + result.stdout)
                    self.assertIn(field, result.stderr + result.stdout)

    def test_rejects_semantic_pass_negative_diff_missing_accepted_ref(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._call_expression_semantic_pass_fixture(Path(tmp))
            prefix = "l3-call-expression"
            negative_path = evidence_dir / f"{prefix}-negative-diff.json"
            negative = json.loads(negative_path.read_text(encoding="utf-8"))
            negative.pop("accepted_negative_diff", None)
            self._write_json(negative_path, negative)
            self._bind_manifest_ref(evidence_dir, prefix, "negative_diff", negative_path, "expected_failed")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "call-expression",
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

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("negative diff", result.stderr + result.stdout)
            self.assertIn("accepted_negative_diff", result.stderr + result.stdout)

    def test_rejects_semantic_pass_negative_diff_missing_gate_fields(self) -> None:
        for field in [
            "negative_diff_gate",
            "accepted_negative_diff_required",
            "blocked_by",
            "root_blocked_by",
            "required_inputs",
        ]:
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
                    spec_path, out_root, evidence_dir = self._call_expression_semantic_pass_fixture(Path(tmp))
                    prefix = "l3-call-expression"
                    negative_path = evidence_dir / f"{prefix}-negative-diff.json"
                    negative = json.loads(negative_path.read_text(encoding="utf-8"))
                    negative.pop(field, None)
                    self._write_json(negative_path, negative)
                    self._bind_manifest_ref(evidence_dir, prefix, "negative_diff", negative_path, "expected_failed")

                    result = subprocess.run(
                        [
                            "python",
                            str(VALIDATOR),
                            "--target-id",
                            "demo",
                            "--slice-id",
                            "call-expression",
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

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("negative diff", result.stderr + result.stdout)
                    self.assertIn(field, result.stderr + result.stdout)

    def test_rejects_semantic_pass_manifest_schema_diff_sha_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._call_expression_semantic_pass_fixture(Path(tmp))
            prefix = "l3-call-expression"
            manifest_path = evidence_dir / f"{prefix}-evidence-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["evidence"]["schema_diff"]["sha256"] = "stale-schema-diff-sha"
            self._write_json(manifest_path, manifest)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "call-expression",
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

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("schema_diff", result.stderr + result.stdout)
            self.assertIn("sha256", result.stderr + result.stdout)

    def test_rejects_semantic_pass_manifest_negative_diff_status_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            spec_path, out_root, evidence_dir = self._call_expression_semantic_pass_fixture(Path(tmp))
            prefix = "l3-call-expression"
            manifest_path = evidence_dir / f"{prefix}-evidence-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["evidence"]["negative_diff"]["status"] = "passed"
            self._write_json(manifest_path, manifest)

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "call-expression",
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

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("negative_diff", result.stderr + result.stdout)
            self.assertIn("status", result.stderr + result.stdout)

    def test_rejects_semantic_pass_manifest_ref_payload_missing_status(self) -> None:
        validator = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            ref_path = Path(tmp) / "payload.json"
            self._write_json(ref_path, {"schema_version": 1, "kind": "unit-test"})
            evidence = {
                "unit_ref": {
                    "path": ref_path.as_posix(),
                    "status": "passed",
                    "sha256": self._sha256(ref_path),
                }
            }

            with self.assertRaises(SystemExit) as raised:
                validator.load_ref(evidence, "unit_ref")

            self.assertIn("unit_ref", str(raised.exception))
            self.assertIn("payload status", str(raised.exception))

    def test_rejects_read_write_pointer_graph_missing_alias_gate_fields(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "demo-copy-i32-ptr-arith.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
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

            pointer_graph_path = (
                out_root
                / "demo"
                / "auto-translation"
                / "copy-i32-ptr-arith"
                / "l3-copy-i32-ptr-arith-pointer-graph.json"
            )
            pointer_graph = json.loads(pointer_graph_path.read_text(encoding="utf-8"))
            for key in ["alias_sets", "alias_risks", "alias_contract", "safe_boundary_preconditions"]:
                pointer_graph.pop(key, None)
            pointer_graph_path.write_text(json.dumps(pointer_graph), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "copy-i32-ptr-arith",
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
            self.assertIn("alias gate", result.stderr + result.stdout)

    def test_rejects_v2_read_write_pointer_graph_missing_effect_graph(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "demo-copy-i32-ptr-arith.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
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

            pointer_graph_path = (
                out_root
                / "demo"
                / "auto-translation"
                / "copy-i32-ptr-arith"
                / "l3-copy-i32-ptr-arith-pointer-graph.json"
            )
            pointer_graph = json.loads(pointer_graph_path.read_text(encoding="utf-8"))
            pointer_graph["schema_version"] = 2
            pointer_graph.pop("effect_graph", None)
            pointer_graph_path.write_text(json.dumps(pointer_graph), encoding="utf-8")
            self._refresh_route_source_artifact_ref(
                pointer_graph_path.parent,
                "copy-i32-ptr-arith",
                "pointer_graph",
                pointer_graph_path,
                "recorded",
            )

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "copy-i32-ptr-arith",
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
            self.assertIn("effect_graph", result.stderr + result.stdout)

    def test_allows_legacy_v1_read_write_pointer_graph_without_effect_graph(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "demo-copy-i32-ptr-arith.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
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

            pointer_graph_path = (
                out_root
                / "demo"
                / "auto-translation"
                / "copy-i32-ptr-arith"
                / "l3-copy-i32-ptr-arith-pointer-graph.json"
            )
            pointer_graph = json.loads(pointer_graph_path.read_text(encoding="utf-8"))
            pointer_graph["schema_version"] = 1
            pointer_graph.pop("effect_graph", None)
            pointer_graph_path.write_text(json.dumps(pointer_graph), encoding="utf-8")
            self._refresh_route_source_artifact_ref(
                pointer_graph_path.parent,
                "copy-i32-ptr-arith",
                "pointer_graph",
                pointer_graph_path,
                "recorded",
            )

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "copy-i32-ptr-arith",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def _write_call_expression_external_callee_spec(self, tmp_path: Path) -> Path:
        spec = json.loads(
            (REPO_ROOT / "validation" / "slice-specs" / "demo-call-expression.json").read_text(
                encoding="utf-8"
            )
        )
        spec["c_boundary"]["signatures"].append(
            {
                "id": "sig-call-expression-chain",
                "role": "external_direct_callee",
                "function": "call_expression_chain",
                "return_type": "int",
                "parameters": [{"name": "value", "c_type": "int"}],
                "source_ref": "unit/call_expression.c#call_expression_chain",
                "signature_sha256": "call-expression-signature-sha",
                "definition_status": "real_source_bound",
                "c_source": "int call_expression_chain(int value) { return value; }",
            }
        )
        spec["c_boundary"]["external_direct_callees"] = [
            {
                "name": "call_expression_chain",
                "signature_ref": "sig-call-expression-chain",
                "source_files": [{"path": "unit/call_expression.c", "sha256": "call-expression-sha"}],
                "definition_status": "real_source_bound",
                "stub_boundary": "compile_only",
            }
        ]
        spec_path = tmp_path / "demo-call-expression-external-callee.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        return spec_path

    def _global_dependency_evidence(self, tmp_path: Path) -> tuple[Path, Path, Path]:
        spec_path = tmp_path / "global-dependency-validator.json"
        spec_path.write_text(json.dumps(self._global_dependency_spec()), encoding="utf-8")
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
        evidence_dir = out_root / "demo" / "auto-translation" / "global-dependency-validator"
        return spec_path, out_root, evidence_dir

    def _call_expression_semantic_pass_fixture(self, tmp_path: Path) -> tuple[Path, Path, Path]:
        out_root = tmp_path / "evidence"
        source_dir = REPO_ROOT / "validation" / "evidence" / "demo" / "auto-translation" / "call-expression"
        evidence_dir = out_root / "demo" / "auto-translation" / "call-expression"
        shutil.copytree(source_dir, evidence_dir)
        self._backfill_route_baseline_profile_evidence(evidence_dir, "demo", "call-expression")
        prefix = "l3-call-expression"
        self._refresh_call_expression_accepted_oracle_binding(evidence_dir, prefix)
        self._assert_call_expression_passed_diff_gate_fields(evidence_dir, prefix)
        self._bind_manifest_ref(evidence_dir, prefix, "schema_diff", evidence_dir / f"{prefix}-diff.json", "passed")
        self._bind_manifest_ref(
            evidence_dir,
            prefix,
            "negative_diff",
            evidence_dir / f"{prefix}-negative-diff.json",
            "expected_failed",
        )
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "demo-call-expression.json"
        return spec_path, out_root, evidence_dir

    def _refresh_call_expression_accepted_oracle_binding(self, evidence_dir: Path, prefix: str) -> None:
        c_oracle_path = evidence_dir / f"{prefix}-c-oracle-status.json"
        c_oracle = json.loads(c_oracle_path.read_text(encoding="utf-8"))
        accepted = c_oracle.get("accepted_oracle")
        if not isinstance(accepted, dict):
            return
        accepted_path = self._repo_path(accepted["path"])
        accepted_sha = self._sha256(accepted_path)
        accepted["sha256"] = accepted_sha
        self._write_json(c_oracle_path, c_oracle)
        self._bind_manifest_ref(evidence_dir, prefix, "c_oracle", c_oracle_path, "C_ORACLE_GENERATED")

        diff_path = evidence_dir / f"{prefix}-diff.json"
        diff = json.loads(diff_path.read_text(encoding="utf-8"))
        self._refresh_embedded_ref_sha(diff, "accepted_diff")
        self._write_json(diff_path, diff)

        negative_path = evidence_dir / f"{prefix}-negative-diff.json"
        negative = json.loads(negative_path.read_text(encoding="utf-8"))
        self._refresh_embedded_ref_sha(negative, "accepted_negative_diff")
        self._write_json(negative_path, negative)

        auto_manifest_path = evidence_dir / f"{prefix}-auto-translation-manifest.json"
        auto_manifest = json.loads(auto_manifest_path.read_text(encoding="utf-8"))
        accepted_binding = auto_manifest["accepted_evidence_binding"]
        for key, path_text in accepted_binding["paths"].items():
            accepted_binding["path_sha256"][key] = self._sha256(self._repo_path(path_text))
        auto_manifest["oracle"]["accepted_oracle"]["sha256"] = accepted_sha
        self._write_json(auto_manifest_path, auto_manifest)

    def _refresh_embedded_ref_sha(self, payload: dict, key: str) -> None:
        ref = payload.get(key)
        if isinstance(ref, dict) and isinstance(ref.get("path"), str):
            ref["sha256"] = self._sha256(self._repo_path(ref["path"]))

    def _repo_path(self, path: str) -> Path:
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = REPO_ROOT / resolved
        return resolved

    def _external_callee_context_payloads(self) -> tuple[dict, dict, dict]:
        signature = {
            "id": "sig-helper-add-one",
            "role": "external_direct_callee",
            "function": "helper_add_one",
            "return_type": "int",
            "parameters": [{"name": "value", "c_type": "int"}],
            "source_ref": "unit/helper.c#helper_add_one",
            "definition_status": "real_source_bound",
        }
        callee = {
            "name": "helper_add_one",
            "signature_ref": "sig-helper-add-one",
            "source_ref": "unit/helper.c#helper_add_one",
            "source_files": [{"path": "unit/helper.c", "sha256": "helper-sha"}],
            "definition_status": "real_source_bound",
            "stub_kind": "compile_only",
            "stub_boundary": "compile_only",
            "semantics_verified": False,
            "parameters": [{"name": "value", "c_type": "int"}],
            "return_type": "int",
            "supported": True,
            "unsupported_reasons": [],
        }
        call_edges = [
            {
                "callee": "helper_add_one",
                "arguments": ["value"],
                "source_expression": "helper_add_one(value)",
                "statement_context": "decl:init:first",
                "callee_scope": "external_direct_callee",
                "callee_signature_id": "sig-helper-add-one",
                "callee_source_ref": "unit/helper.c#helper_add_one",
                "definition_status": "real_source_bound",
                "stub_status": "compile_only",
            },
            {
                "callee": "helper_add_one",
                "arguments": ["first"],
                "source_expression": "helper_add_one(first)",
                "statement_context": "assign:value",
                "callee_scope": "external_direct_callee",
                "callee_signature_id": "sig-helper-add-one",
                "callee_source_ref": "unit/helper.c#helper_add_one",
                "definition_status": "real_source_bound",
                "stub_status": "compile_only",
            },
            {
                "callee": "helper_add_one",
                "arguments": ["value"],
                "source_expression": "helper_add_one(value)",
                "statement_context": "return:value",
                "callee_scope": "external_direct_callee",
                "callee_signature_id": "sig-helper-add-one",
                "callee_source_ref": "unit/helper.c#helper_add_one",
                "definition_status": "real_source_bound",
                "stub_status": "compile_only",
            },
        ]
        slice_spec = {
            "c_boundary": {
                "signatures": [signature],
                "external_direct_callees": [
                    {
                        "name": "helper_add_one",
                        "signature_ref": "sig-helper-add-one",
                        "source_files": [{"path": "unit/helper.c", "sha256": "helper-sha"}],
                    }
                ],
            }
        }
        plan = {
            "translation_summary": {
                "external_direct_callees": [callee],
                "external_direct_callee_blocks": [],
                "call_expressions": json.loads(json.dumps(call_edges)),
            }
        }
        context = {
            "external_direct_callees": [callee],
            "external_direct_callee_blocks": [],
            "direct_call_edges": json.loads(json.dumps(call_edges)),
            "signature_bindings": [
                {
                    "callee": "helper_add_one",
                    "signature_ref": "sig-helper-add-one",
                    "definition_status": "real_source_bound",
                    "stub_kind": "compile_only",
                    "semantics_verified": False,
                }
            ],
            "callee_sources": [
                {"callee": "helper_add_one", "path": "unit/helper.c", "sha256": "helper-sha"}
            ],
            "call_edge_to_callee_binding": [
                {
                    "callee": call["callee"],
                    "signature_ref": "sig-helper-add-one",
                    "source_expression": call["source_expression"],
                    "statement_context": call["statement_context"],
                    "stub_kind": "compile_only",
                    "semantics_verified": False,
                }
                for call in call_edges
            ],
        }
        return slice_spec, plan, context

    def _blocked_external_callee_context_payloads(self) -> tuple[dict, dict, dict]:
        signature = {
            "id": "sig-helper-box",
            "role": "external_direct_callee",
            "function": "helper_box",
            "return_type": "struct helper_box",
            "parameters": [{"name": "value", "c_type": "int"}],
            "source_ref": "unit/helper.c#helper_box",
            "definition_status": "real_source_bound",
        }
        block = {
            "name": "helper_box",
            "reason": "unsupported_external_direct_callee_signature",
            "unsupported_reasons": ["unsupported_return_type"],
            "stub_kind": "none",
            "semantics_verified": False,
        }
        call_edges = [
            {
                "callee": "helper_box",
                "arguments": ["value"],
                "source_expression": "helper_box(value)",
                "statement_context": "return:value",
                "callee_scope": "external_direct_callee",
                "stub_status": "blocked",
                "blocked_reason": "unsupported_external_direct_callee_signature",
            }
        ]
        slice_spec = {
            "c_boundary": {
                "signatures": [signature],
                "external_direct_callees": [
                    {
                        "name": "helper_box",
                        "signature_ref": "sig-helper-box",
                        "source_files": [{"path": "unit/helper.c", "sha256": "helper-sha"}],
                    }
                ],
            }
        }
        plan = {
            "translation_summary": {
                "external_direct_callees": [],
                "external_direct_callee_blocks": [block],
                "call_expressions": json.loads(json.dumps(call_edges)),
            }
        }
        context = {
            "external_direct_callees": [],
            "external_direct_callee_blocks": [block],
            "direct_call_edges": json.loads(json.dumps(call_edges)),
            "signature_bindings": [],
            "callee_sources": [],
            "call_edge_to_callee_binding": [],
        }
        return slice_spec, plan, context

    def _external_callee_manifest_scope(self) -> dict:
        return {
            "claim_boundary": {
                "external_callee_scope": {
                    "stub_kind": "compile_only",
                    "semantics_verified": False,
                }
            },
            "external_callee_scope": {
                "stub_kind": "compile_only",
                "semantics_verified": False,
            },
        }

    def _blocked_external_callee_manifest_scope(self) -> dict:
        return {
            "claim_boundary": {
                "external_callee_scope": {
                    "stub_kind": "none",
                    "semantics_verified": False,
                }
            },
            "external_callee_scope": {
                "stub_kind": "none",
                "semantics_verified": False,
            },
        }

    def _promote_call_expression_fixture_to_l4_authoritative(self, evidence_dir: Path) -> None:
        prefix = "l3-call-expression"
        route_path = evidence_dir / f"{prefix}-route-decision.json"
        profile_path = evidence_dir / f"{prefix}-validation-profile.json"

        route = json.loads(route_path.read_text(encoding="utf-8"))
        route["status"] = "refused"
        route["level"] = "L4"
        route["translator"] = {"kind": "refuse", "candidate_generation_allowed": False}
        route["verification_profile"] = "L4-accepted-evidence"
        route["rationale"] = [{"feature": "accepted_evidence_authoritative", "weight": "override"}]
        route["policy"]["accepted_evidence_authoritative"] = True
        route["policy"]["generated_draft_semantic_pass"] = False
        self._write_json(route_path, route)

        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile["status"] = "passed"
        profile["profile"] = "L4-accepted-evidence"
        profile["route_level"] = "L4"
        profile["skipped_gates"] = []
        profile["accepted_evidence_authoritative"] = True
        profile["generated_draft_semantic_pass"] = False
        self._write_json(profile_path, profile)

        route_ref = self._ref(route_path, "refused")
        route_ref["level"] = "L4"
        profile_ref = self._ref(profile_path, "passed")
        profile_ref["profile"] = "L4-accepted-evidence"

        final_path = evidence_dir / f"{prefix}-final-verification.json"
        final = json.loads(final_path.read_text(encoding="utf-8"))
        final["route_decision"] = route_ref
        final["validation_profile"] = profile_ref
        final["validation_profile_status"] = "passed"
        final["skipped_gates"] = []
        final["accepted_evidence_authoritative"] = True
        final["generated_draft_semantic_pass"] = False
        self._write_json(final_path, final)

        cache_path = evidence_dir / f"{prefix}-auto-cache-metadata.json"
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        cache["route_decision_identity"] = {"status": "refused", "sha256": self._sha256_json(route)}
        cache["validation_profile_identity"] = {"status": "passed", "sha256": self._sha256_json(profile)}
        cache["dependent_artifacts"]["route_decision"] = route_ref
        cache["dependent_artifacts"]["validation_profile"] = profile_ref
        self._write_json(cache_path, cache)

        auto_manifest_path = evidence_dir / f"{prefix}-auto-translation-manifest.json"
        auto_manifest = json.loads(auto_manifest_path.read_text(encoding="utf-8"))
        auto_manifest["route_decision"] = route_ref
        auto_manifest["validation_profile"] = profile_ref
        auto_manifest["claim_boundary"]["accepted_evidence_authoritative"] = True
        auto_manifest["claim_boundary"]["generated_draft_semantic_pass"] = False
        self._write_json(auto_manifest_path, auto_manifest)

        manifest_path = evidence_dir / f"{prefix}-evidence-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["evidence"]["route_decision"] = route_ref
        manifest["evidence"]["validation_profile"] = profile_ref
        manifest["evidence"]["final_verification"] = self._ref(final_path, "passed")
        manifest["evidence"]["cache_metadata"] = self._ref(cache_path, "recorded")
        manifest["claim_boundary"]["accepted_evidence_authoritative"] = True
        manifest["claim_boundary"]["generated_draft_semantic_pass"] = False
        self._write_json(manifest_path, manifest)

    def _add_call_expression_oracle_boundary_contract(self, evidence_dir: Path) -> None:
        prefix = "l3-call-expression"
        profile_path = evidence_dir / f"{prefix}-validation-profile.json"
        final_path = evidence_dir / f"{prefix}-final-verification.json"
        cache_path = evidence_dir / f"{prefix}-auto-cache-metadata.json"
        auto_manifest_path = evidence_dir / f"{prefix}-auto-translation-manifest.json"
        manifest_path = evidence_dir / f"{prefix}-evidence-manifest.json"
        contract = self._call_expression_oracle_boundary_contract()

        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile["oracle_boundary_contract"] = contract
        self._write_json(profile_path, profile)
        profile_ref = self._ref(profile_path, profile.get("status", "passed"))
        profile_ref["profile"] = profile.get("profile")

        final = json.loads(final_path.read_text(encoding="utf-8"))
        final["oracle_boundary_contract"] = contract
        final["validation_profile"] = profile_ref
        self._write_json(final_path, final)
        final_ref = self._ref(final_path, final.get("status", "passed"))

        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        cache["validation_profile_identity"] = {
            "status": profile.get("status", "unknown"),
            "sha256": self._sha256_json(profile),
        }
        cache["oracle_boundary_contract_identity"] = {
            "status": contract.get("status", "unknown"),
            "sha256": self._sha256_json(contract),
        }
        fields = cache.setdefault("cache_input_fields", [])
        if "oracle_boundary_contract_identity" not in fields:
            fields.append("oracle_boundary_contract_identity")
        cache["dependent_artifacts"]["validation_profile"] = profile_ref
        self._write_json(cache_path, cache)
        cache_ref = self._ref(cache_path, "recorded")

        auto_manifest = json.loads(auto_manifest_path.read_text(encoding="utf-8"))
        auto_manifest["validation_profile"] = profile_ref
        self._write_json(auto_manifest_path, auto_manifest)

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["evidence"]["validation_profile"] = profile_ref
        manifest["evidence"]["final_verification"] = final_ref
        manifest["evidence"]["cache_metadata"] = cache_ref
        self._write_json(manifest_path, manifest)

    def _refresh_call_expression_validation_profile_refs(self, evidence_dir: Path) -> None:
        prefix = "l3-call-expression"
        profile_path = evidence_dir / f"{prefix}-validation-profile.json"
        final_path = evidence_dir / f"{prefix}-final-verification.json"
        cache_path = evidence_dir / f"{prefix}-auto-cache-metadata.json"
        auto_manifest_path = evidence_dir / f"{prefix}-auto-translation-manifest.json"
        manifest_path = evidence_dir / f"{prefix}-evidence-manifest.json"

        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile_ref = self._ref(profile_path, profile.get("status", "passed"))
        profile_ref["profile"] = profile.get("profile")

        final = json.loads(final_path.read_text(encoding="utf-8"))
        final["validation_profile"] = profile_ref
        self._write_json(final_path, final)
        final_ref = self._ref(final_path, final.get("status", "passed"))

        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        cache["validation_profile_identity"] = {
            "status": profile.get("status", "unknown"),
            "sha256": self._sha256_json(profile),
        }
        contract = profile.get("oracle_boundary_contract", {})
        cache["oracle_boundary_contract_identity"] = {
            "status": contract.get("status", "unknown"),
            "sha256": self._sha256_json(contract),
        }
        fields = cache.setdefault("cache_input_fields", [])
        if "oracle_boundary_contract_identity" not in fields:
            fields.append("oracle_boundary_contract_identity")
        cache["dependent_artifacts"]["validation_profile"] = profile_ref
        self._write_json(cache_path, cache)
        cache_ref = self._ref(cache_path, "recorded")

        auto_manifest = json.loads(auto_manifest_path.read_text(encoding="utf-8"))
        auto_manifest["validation_profile"] = profile_ref
        self._write_json(auto_manifest_path, auto_manifest)

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["evidence"]["validation_profile"] = profile_ref
        manifest["evidence"]["final_verification"] = final_ref
        manifest["evidence"]["cache_metadata"] = cache_ref
        self._write_json(manifest_path, manifest)

    def _call_expression_oracle_boundary_contract(self) -> dict:
        return {
            "schema_version": 1,
            "status": "sufficient_for_semantic_pass",
            "insufficient_reasons": [],
            "observable_outputs": [
                "return_value",
                "status",
                "call_expression_count",
                "call_expression_contexts",
                "source_calls",
            ],
            "fixture_representativeness": {
                "fixture_path": "validation/l2_slices/fixtures/call-expression-c-oracle.json",
                "fixture_hash": "call-expression-fixture",
                "declared_case_count": 4,
                "accepted_oracle_case_count": 7,
                "case_source": "fixture_contract",
                "representativeness": "bounded_fixture_contract",
                "limitations": [],
            },
            "compiler": {
                "command_source": "validation/l2_slices/tools/generate_call_expression_oracle.py",
                "include_paths": [],
                "defines": [],
                "flags": [],
                "tool_versions": {
                    "gcc": "captured_by_wsl_oracle",
                    "rustc": "captured_at_validation",
                },
            },
            "target": {
                "triple_or_abi": "x86_64-unknown-linux-gnu",
                "endianness": "little",
                "int_width": 32,
                "long_width": 64,
                "pointer_width": 64,
                "word_size_bits": 64,
            },
            "sanitizer_diagnostics": {
                "sanitizer_status": "not_run",
                "diagnostic_status": "recorded",
                "diagnostics": ["demo slice uses explicit C source and no external headers"],
                "clang_type_extraction_available": False,
            },
            "ub_and_implementation_defined": {
                "known_ub": [],
                "implementation_defined_behavior": [],
                "scalar_arithmetic_contract": {},
            },
            "platform_model": {
                "hardware_dependencies": [],
                "rtos_dependencies": [],
                "volatile_dependencies": [],
                "hardware_dependency_status": "not_applicable",
                "rtos_dependency_status": "not_applicable",
                "volatile_dependency_status": "not_applicable",
            },
        }

    def _assert_call_expression_passed_diff_gate_fields(self, evidence_dir: Path, prefix: str) -> None:
        diff_path = evidence_dir / f"{prefix}-diff.json"
        diff = json.loads(diff_path.read_text(encoding="utf-8"))
        self.assertEqual(diff.get("diff_gate"), "schema_aware_c_rust_diff")
        self.assertIs(diff.get("accepted_diff_required"), True)
        self.assertEqual(diff.get("blocked_by"), [])
        diff_required_inputs = diff.get("required_inputs")
        self.assertIsInstance(diff_required_inputs, dict)
        self.assertEqual(diff_required_inputs.get("c_oracle_required_status"), "C_ORACLE_GENERATED")
        self.assertEqual(diff_required_inputs.get("rust_report_required_status"), "passed")
        self.assertEqual(diff_required_inputs.get("schema_diff_actual_status"), "passed")

        negative_path = evidence_dir / f"{prefix}-negative-diff.json"
        negative = json.loads(negative_path.read_text(encoding="utf-8"))
        self.assertEqual(negative.get("negative_diff_gate"), "schema_aware_negative_diff")
        self.assertIs(negative.get("accepted_negative_diff_required"), True)
        self.assertEqual(negative.get("blocked_by"), [])
        self.assertEqual(negative.get("root_blocked_by"), [])
        negative_required_inputs = negative.get("required_inputs")
        self.assertIsInstance(negative_required_inputs, dict)
        self.assertEqual(negative_required_inputs.get("schema_diff_required_status"), "passed")
        self.assertIsNone(negative_required_inputs.get("schema_diff_required_first_mismatch"))
        self.assertEqual(negative_required_inputs.get("schema_diff_actual_status"), "passed")

    def _bind_manifest_ref(
        self,
        evidence_dir: Path,
        prefix: str,
        evidence_key: str,
        artifact_path: Path,
        artifact_status: str,
    ) -> None:
        manifest_path = evidence_dir / f"{prefix}-evidence-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        ref = self._ref(artifact_path, artifact_status)
        if evidence_key == "negative_diff":
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            ref["expected_failure"] = bool(payload.get("expected_failure"))
            ref["mutation_detected"] = bool(payload.get("mutation_detected") or payload.get("detected"))
        manifest["evidence"][evidence_key] = ref
        self._write_json(manifest_path, manifest)

    def _global_dependency_spec(self) -> dict:
        return {
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "global-dependency-validator",
            "level": "L3",
            "status": "ready",
            "source_commit": "1234567",
            "function_name": "global_dependency_validator",
            "c_source": "int global_dependency_validator(int value) { return value + 1; }",
            "fixture_hash": "fixture",
            "l1_evidence": {
                "path": "validation/evidence/demo/l1-native-build.json",
                "status": "test",
                "accepted": False,
            },
            "source": {
                "source_root": "unit",
                "source_commit": "1234567",
                "repo_commit": "1234567",
                "source_file_hashes": {"unit/global.c": "global-sha"},
            },
            "build_profile": {
                "profile_id": "demo-global-dependency-validator-auto-profile",
                "compiler_command_source": "unit-test",
                "include_paths": ["inc"],
                "defines": [],
                "target": {
                    "triple_or_abi": "x86_64-unknown-linux-gnu",
                    "endianness": "little",
                    "int_width": 32,
                    "long_width": 64,
                    "pointer_width": 64,
                },
                "preprocessing_mode": "manual_flags",
                "tool_versions": {"cc": "unit-test"},
                "clang_type_extraction": {"available": False, "diagnostics": ["unit-test"]},
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "fixture_id": "unit-fixture",
                "path": "unit-test-fixture.json",
                "hash": "fixture",
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
                "functions": ["global_dependency_validator"],
                "signatures": [
                    {
                        "function": "global_dependency_validator",
                        "return_type": "int",
                        "parameters": [{"name": "value", "c_type": "int"}],
                    }
                ],
                "direct_dependencies": [
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
                    }
                ],
            },
            "rust_boundary": {
                "crate": "validation/l2_slices",
                "module": "validation/l2_slices/src/global_dependency_validator.rs",
                "public_api": [
                    {
                        "name": "global_dependency_validator",
                        "visibility": "public",
                        "boundary_kind": "internal_ffi",
                    }
                ],
                "raw_pointer_policy": "internal_only",
                "unsafe_policy": {"max_first_party_non_test_ratio": 0.1, "ledger_required": True},
            },
            "claim_boundary": {
                "accepted_metadata_differences": [],
                "non_goals": ["unit test only"],
                "must_not_claim": ["semantic equivalence without C oracle"],
            },
            "cache_invalidation_keys": ["unit-test"],
        }

    def _backfill_route_baseline_profile_evidence(self, evidence_dir: Path, target_id: str, slice_id: str) -> None:
        prefix = f"l3-{slice_id}"
        manifest_path = evidence_dir / f"{prefix}-evidence-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_commit = manifest.get("source_commit", "UNKNOWN0")
        baseline_path = evidence_dir / f"{prefix}-c2rust-baseline-manifest.json"
        route_path = evidence_dir / f"{prefix}-route-decision.json"
        profile_path = evidence_dir / f"{prefix}-validation-profile.json"

        baseline = {
            "schema_version": 1,
            "target_id": target_id,
            "slice_id": slice_id,
            "status": "skipped",
            "reason": "unit_test_backfill_for_legacy_fixture",
            "correctness_role": "candidate_context_only",
            "fallback_oracle": "original_c_oracle_required",
            "validation_impact": "legacy fixture backfill only; accepted gates remain authoritative",
            "source_commit": source_commit,
            "slice_spec": {"path": f"validation/slice-specs/demo-{slice_id}.json", "sha256": "legacy-fixture"},
            "build_profile_hash": "legacy-fixture",
            "commands": [],
            "selected_command": None,
            "reference_tree": {"path": "F:/agent/c2rust-master", "status": "missing", "cargo_toml": ""},
            "output": None,
            "diagnostics": ["legacy fixture backfill"],
        }
        self._write_json(baseline_path, baseline)

        route = {
            "schema_version": 1,
            "target_id": target_id,
            "slice_id": slice_id,
            "status": "recorded",
            "level": "L0",
            "translator": {"kind": "tier1", "candidate_generation_allowed": True},
            "rationale": [{"feature": "legacy_fixture_backfill", "weight": "low"}],
            "verification_profile": "L0-dev",
            "source_artifacts": {
                "type_map": self._ref(evidence_dir / f"{prefix}-type-map.json", "recorded"),
                "cfg": self._ref(evidence_dir / f"{prefix}-cfg.json", "recorded"),
                "pointer_graph": self._ref(evidence_dir / f"{prefix}-pointer-graph.json", "not_applicable"),
                "translation_plan": self._ref(evidence_dir / f"{prefix}-auto-translation-plan.json", "draft_generated"),
                "c2rust_baseline": self._ref(baseline_path, "skipped"),
            },
            "policy": {
                "goal": "dev",
                "fixed_loop_count_required": False,
                "repair_budget_source": "run_policy",
            },
            "misroute": None,
        }
        self._write_json(route_path, route)

        contract = self._call_expression_oracle_boundary_contract()
        profile = {
            "schema_version": 1,
            "target_id": target_id,
            "slice_id": slice_id,
            "status": "passed",
            "profile": "L0-dev",
            "route_level": "L0",
            "goal": "dev",
            "required_gates": ["compile", "c_oracle_diff"],
            "optional_gates": ["negative_diff", "evidence_cleanliness", "fuzz_property", "miri", "kani"],
            "skipped_gates": [],
            "required_gate_status": {"compile": "passed", "c_oracle_diff": "C_ORACLE_GENERATED"},
            "loop_policy": {"source": "run_policy", "fixed_project_loop_count_required": False, "stress_loops": None},
            "tool_boundaries": {
                "c_ub": ["clang_diagnostics", "sanitizer_oracle", "unsupported_evidence"],
                "rust_ub": ["miri", "unsafe_ledger", "rust_verification_tools"],
            },
            "oracle_boundary_contract": contract,
        }
        self._write_json(profile_path, profile)

        route_ref = self._ref(route_path, "recorded")
        route_ref["level"] = "L0"
        profile_ref = self._ref(profile_path, "passed")
        profile_ref["profile"] = "L0-dev"
        baseline_ref = self._ref(baseline_path, "skipped")

        final_path = evidence_dir / f"{prefix}-final-verification.json"
        final = json.loads(final_path.read_text(encoding="utf-8"))
        final["c2rust_baseline"] = baseline_ref
        final["route_decision"] = route_ref
        final["validation_profile"] = profile_ref
        final["skipped_gates"] = []
        final["validation_profile_status"] = "passed"
        final["oracle_boundary_contract"] = contract
        self._write_json(final_path, final)

        cache_path = evidence_dir / f"{prefix}-auto-cache-metadata.json"
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        cache["c2rust_baseline_identity"] = {"status": "skipped", "sha256": self._sha256_json(baseline)}
        cache["route_decision_identity"] = {"status": "recorded", "sha256": self._sha256_json(route)}
        cache["validation_profile_identity"] = {"status": "passed", "sha256": self._sha256_json(profile)}
        cache["oracle_boundary_contract_identity"] = {
            "status": contract["status"],
            "sha256": self._sha256_json(contract),
        }
        fields = cache.setdefault("cache_input_fields", [])
        for key in [
            "c2rust_baseline_identity",
            "route_decision_identity",
            "validation_profile_identity",
            "oracle_boundary_contract_identity",
        ]:
            if key not in fields:
                fields.append(key)
        cache["dependent_artifacts"] = {
            "c2rust_baseline": baseline_ref,
            "route_decision": route_ref,
            "validation_profile": profile_ref,
        }
        self._write_json(cache_path, cache)

        auto_manifest_path = evidence_dir / f"{prefix}-auto-translation-manifest.json"
        if auto_manifest_path.exists():
            auto_manifest = json.loads(auto_manifest_path.read_text(encoding="utf-8"))
            auto_manifest["c2rust_baseline"] = baseline_ref
            auto_manifest["route_decision"] = route_ref
            auto_manifest["validation_profile"] = profile_ref
            self._write_json(auto_manifest_path, auto_manifest)

        manifest["evidence"]["c2rust_baseline"] = baseline_ref
        manifest["evidence"]["route_decision"] = route_ref
        manifest["evidence"]["validation_profile"] = profile_ref
        manifest["evidence"]["final_verification"] = self._ref(final_path, final.get("status", "passed"))
        manifest["evidence"]["cache_metadata"] = self._ref(cache_path, "recorded")
        self._write_json(manifest_path, manifest)

    def _candidate_selection_record(self) -> dict:
        c2rust_candidate = {
            "candidate_id": "c2rust-baseline",
            "kind": "c2rust-baseline",
            "status": "skipped",
            "role": "baseline_or_repair_candidate_context",
            "correctness_role": "candidate_context_only",
            "reason": "blocked_by_missing_tools",
            "semantic_pass": False,
        }
        return {
            "selection_policy": {
                "stage": "post_generation_provenance",
                "selection_basis": "translator_artifact_primary_candidate",
                "semantic_acceptance": False,
                "full_router": False,
            },
            "selected_candidate_id": None,
            "candidate_set": [
                {
                    "candidate_id": "compat:legacy-string-translator",
                    "kind": "legacy-string-translator",
                    "status": "generated",
                    "role": "compatibility_rust_draft",
                    "correctness_role": "compatibility_only",
                    "compatibility_only": True,
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

    def _refresh_route_source_artifact_ref(
        self,
        evidence_dir: Path,
        slice_id: str,
        artifact_key: str,
        artifact_path: Path,
        artifact_status: str,
    ) -> None:
        prefix = f"l3-{slice_id}"
        route_path = evidence_dir / f"{prefix}-route-decision.json"
        route = json.loads(route_path.read_text(encoding="utf-8"))
        route["source_artifacts"][artifact_key] = self._ref(artifact_path, artifact_status)
        self._write_json(route_path, route)

        route_ref = self._ref(route_path, route.get("status", "recorded"))
        if route.get("level"):
            route_ref["level"] = route["level"]

        for path, key_path in [
            (evidence_dir / f"{prefix}-auto-translation-manifest.json", ("route_decision",)),
            (evidence_dir / f"{prefix}-evidence-manifest.json", ("evidence", "route_decision")),
            (evidence_dir / f"{prefix}-final-verification.json", ("route_decision",)),
            (evidence_dir / f"{prefix}-auto-cache-metadata.json", ("dependent_artifacts", "route_decision")),
        ]:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if len(key_path) == 1:
                payload[key_path[0]] = route_ref
            else:
                payload[key_path[0]][key_path[1]] = route_ref
            if path.name.endswith("-auto-cache-metadata.json"):
                payload["route_decision_identity"] = {
                    "status": route.get("status", "unknown"),
                    "sha256": self._sha256_json(route),
                }
            self._write_json(path, payload)

    def _ref(self, path: Path, status: str) -> dict:
        return {"path": path.as_posix(), "status": status, "sha256": self._sha256(path)}

    def _write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _sha256_json(self, payload: dict) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def test_rejects_missing_alias_gate_in_manifest_and_final_verification(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "demo-copy-i32-ptr-arith.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
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

            evidence_dir = out_root / "demo" / "auto-translation" / "copy-i32-ptr-arith"
            for file_name in [
                "l3-copy-i32-ptr-arith-evidence-manifest.json",
                "l3-copy-i32-ptr-arith-final-verification.json",
            ]:
                path = evidence_dir / file_name
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload.get("claim_boundary", {}).pop("alias_gate", None)
                payload.pop("alias_gate", None)
                path.write_text(json.dumps(payload), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "copy-i32-ptr-arith",
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
            self.assertIn("alias gate", result.stderr + result.stdout)

    def test_rejects_empty_alias_risk_and_noalias_precondition_for_unknown_alias(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "demo-copy-i32-ptr-arith.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
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

            pointer_graph_path = (
                out_root
                / "demo"
                / "auto-translation"
                / "copy-i32-ptr-arith"
                / "l3-copy-i32-ptr-arith-pointer-graph.json"
            )
            pointer_graph = json.loads(pointer_graph_path.read_text(encoding="utf-8"))
            pointer_graph["alias_risks"] = []
            pointer_graph["safe_boundary_preconditions"] = []
            pointer_graph_path.write_text(json.dumps(pointer_graph), encoding="utf-8")

            result = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "copy-i32-ptr-arith",
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
            self.assertIn("alias gate", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
