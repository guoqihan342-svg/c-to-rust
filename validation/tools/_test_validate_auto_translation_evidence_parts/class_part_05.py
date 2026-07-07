class _ValidateAutoTranslationEvidenceTestsPart05:
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
        return self._external_callee_manifest_scope_with_stub_kind("compile_only")

    def _external_callee_manifest_scope_with_stub_kind(self, stub_kind: str) -> dict:
        return {
            "claim_boundary": {
                "external_callee_scope": {
                    "stub_kind": stub_kind,
                    "semantics_verified": False,
                }
            },
            "external_callee_scope": {
                "stub_kind": stub_kind,
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

    def _refresh_manifest_evidence_ref_hashes(self, evidence_dir: Path, prefix: str) -> None:
        manifest_path = evidence_dir / f"{prefix}-evidence-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for ref in manifest.get("evidence", {}).values():
            if not isinstance(ref, dict) or not isinstance(ref.get("path"), str):
                continue
            resolved = self._repo_path(ref["path"])
            if resolved.exists():
                ref["sha256"] = self._sha256(resolved)
        self._write_json(manifest_path, manifest)

    def _install_generated_c2rust_baseline_for_verified_tests(
        self,
        evidence_dir: Path,
        prefix: str,
    ) -> tuple[dict, dict, dict]:
        baseline_path = evidence_dir / f"{prefix}-c2rust-baseline-manifest.json"
        output_path = evidence_dir / f"{prefix}-c2rust-baseline-output.rs"
        artifact_path = evidence_dir / f"{prefix}-c2rust-baseline-output.rlib"
        compile_commands_path = evidence_dir / f"{prefix}-c2rust-compile-commands" / "compile_commands.json"
        stdout_path = evidence_dir / f"{prefix}-c2rust-baseline.stdout.log"
        stderr_path = evidence_dir / f"{prefix}-c2rust-baseline.stderr.log"
        compile_stdout_path = evidence_dir / f"{prefix}-c2rust-baseline-compile.stdout.log"
        compile_stderr_path = evidence_dir / f"{prefix}-c2rust-baseline-compile.stderr.log"
        generated_src_path = evidence_dir / f"{prefix}-c2rust-baseline-generated" / "src" / "lib.rs"
        compile_commands_path.parent.mkdir(parents=True, exist_ok=True)
        generated_src_path.parent.mkdir(parents=True, exist_ok=True)
        compile_commands_path.write_text("[]\n", encoding="utf-8")
        stdout_path.write_text("generated\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        compile_stdout_path.write_text("compiled\n", encoding="utf-8")
        compile_stderr_path.write_text("", encoding="utf-8")
        generated_src_path.write_text("pub fn generated_by_c2rust() {}\n", encoding="utf-8")
        output_path.write_text("pub fn generated_by_c2rust() {}\n", encoding="utf-8")
        artifact_path.write_text("fake rlib\n", encoding="utf-8")
        output_ref = {
            "path": output_path.as_posix(),
            "status": "generated",
            "sha256": self._sha256(output_path),
        }
        compile_ref = {
            "path": artifact_path.as_posix(),
            "status": "compiled",
            "sha256": self._sha256(artifact_path),
        }
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline.update(
            {
                "status": "generated",
                "reason": "generated_by_c2rust",
                "selected_command": {
                    "argv": ["c2rust-transpile", str(compile_commands_path)],
                    "working_directory": ".",
                },
                "output": dict(output_ref),
                "generation": {
                    "compile_commands": {
                        "path": compile_commands_path.as_posix(),
                        "sha256": self._sha256(compile_commands_path),
                    },
                    "command": {
                        "argv": ["c2rust-transpile", str(compile_commands_path)],
                        "working_directory": ".",
                        "stdout_log": stdout_path.as_posix(),
                        "stderr_log": stderr_path.as_posix(),
                        "timeout_seconds": 300,
                        "exit_status": "passed",
                        "returncode": 0,
                    },
                    "generated_files": [
                        {
                            "path": generated_src_path.as_posix(),
                            "sha256": self._sha256(generated_src_path),
                        }
                    ],
                },
                "compile": {
                    "status": "passed",
                    "attempted": True,
                    "semantic_pass": False,
                    "candidate_output": dict(output_ref),
                    "command": {
                        "argv": ["cargo", "check", "--manifest-path", "Cargo.toml"],
                        "working_directory": ".",
                        "stdout_log": compile_stdout_path.as_posix(),
                        "stderr_log": compile_stderr_path.as_posix(),
                        "timeout_seconds": 120,
                        "exit_status": "passed",
                        "returncode": 0,
                    },
                    "artifact": dict(compile_ref),
                    "diagnostics": [],
                },
            }
        )
        self._write_json(baseline_path, baseline)
        baseline_ref = self._ref(baseline_path, "generated")

        route_path = evidence_dir / f"{prefix}-route-decision.json"
        route = json.loads(route_path.read_text(encoding="utf-8"))
        route["source_artifacts"]["c2rust_baseline"] = baseline_ref
        self._write_json(route_path, route)
        route_ref = self._ref(route_path, route.get("status", "recorded"))
        if route.get("level") is not None:
            route_ref["level"] = route.get("level")

        auto_manifest_path = evidence_dir / f"{prefix}-auto-translation-manifest.json"
        auto_manifest = json.loads(auto_manifest_path.read_text(encoding="utf-8"))
        auto_manifest["route_decision"] = route_ref
        auto_manifest["c2rust_baseline"] = baseline_ref
        self._write_json(auto_manifest_path, auto_manifest)

        manifest_path = evidence_dir / f"{prefix}-evidence-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["evidence"]["route_decision"] = route_ref
        manifest["evidence"]["c2rust_baseline"] = baseline_ref
        self._write_json(manifest_path, manifest)

        final_path = evidence_dir / f"{prefix}-final-verification.json"
        final = json.loads(final_path.read_text(encoding="utf-8"))
        final["route_decision"] = route_ref
        final["c2rust_baseline"] = baseline_ref
        self._write_json(final_path, final)

        cache_path = evidence_dir / f"{prefix}-auto-cache-metadata.json"
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        cache["route_decision_identity"] = {"status": "recorded", "sha256": self._sha256_json(route)}
        cache["c2rust_baseline_identity"] = {"status": "generated", "sha256": self._sha256_json(baseline)}
        cache.setdefault("cache_input_fields", [])
        if "route_decision_identity" not in cache["cache_input_fields"]:
            cache["cache_input_fields"].append("route_decision_identity")
        if "c2rust_baseline_identity" not in cache["cache_input_fields"]:
            cache["cache_input_fields"].append("c2rust_baseline_identity")
        cache.setdefault("dependent_artifacts", {})["route_decision"] = route_ref
        cache.setdefault("dependent_artifacts", {})["c2rust_baseline"] = baseline_ref
        self._write_json(cache_path, cache)

        return output_ref, compile_ref, baseline_ref

    def _install_verified_baseline_direct_replay_for_tests(
        self,
        evidence_dir: Path,
        prefix: str,
        baseline_ref: dict,
        output_ref: dict,
        compile_ref: dict,
        *,
        direct_output_ref: dict | None = None,
    ) -> None:
        direct_path = evidence_dir / f"{prefix}-c2rust-direct-replay.json"
        direct_payload = {
            "schema_version": 1,
            "status": "passed",
            "observable_replay_pass": True,
            "semantic_pass": False,
            "generated_draft_semantic_pass": False,
            "replay_kind": "direct_c2rust_output_replay",
            "correctness_role": "direct_replay_evidence",
            "c2rust_output": dict(direct_output_ref or output_ref),
            "compile_artifact": dict(compile_ref),
            "results": {"case_count": 1, "cases": [{"id": "case-one", "matched": True}]},
        }
        self._write_json(direct_path, direct_payload)

        verified_path = evidence_dir / f"{prefix}-c2rust-verified-unsafe-baseline.json"
        verified_payload = {
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": prefix.removeprefix("l3-"),
            "source_commit": "1234567",
            "entry_function": prefix.removeprefix("l3-").replace("-", "_"),
            "status": "blocked",
            "semantic_pass": False,
            "semantic_claim_source": "blocked_missing_c2rust_bound_gates",
            "generated_draft_semantic_pass": False,
            "c2rust_baseline": baseline_ref,
            "c2rust_output": dict(output_ref),
            "compile_artifact": dict(compile_ref),
            "fixture": {
                "path": "validation/l2_slices/fixtures/call-expression-c-oracle.json",
                "hash": "call-expression-fixture",
            },
            "route_decision": self._ref(
                evidence_dir / f"{prefix}-route-decision.json",
                json.loads((evidence_dir / f"{prefix}-route-decision.json").read_text(encoding="utf-8")).get(
                    "status",
                    "recorded",
                ),
            ),
            "validation_profile": self._ref(
                evidence_dir / f"{prefix}-validation-profile.json",
                json.loads((evidence_dir / f"{prefix}-validation-profile.json").read_text(encoding="utf-8")).get(
                    "status",
                    "incomplete",
                ),
            ),
            "direct_c2rust_replay": {
                "status": "passed",
                "semantic_pass": False,
                "observable_replay_pass": True,
                "artifact": self._ref(direct_path, "passed"),
                "c2rust_output": dict(direct_output_ref or output_ref),
                "compile_artifact": dict(compile_ref),
            },
            "blocked_reasons": ["c2rust_bound_gate_refs_not_implemented"],
            "claim_boundary": {
                "semantic_pass": False,
                "generated_draft_semantic_pass": False,
                "compile_only_is_semantic_pass": False,
            },
        }
        self._write_json(verified_path, verified_payload)
        verified_ref = self._ref(verified_path, "blocked")

        auto_manifest_path = evidence_dir / f"{prefix}-auto-translation-manifest.json"
        auto_manifest = json.loads(auto_manifest_path.read_text(encoding="utf-8"))
        auto_manifest["verified_unsafe_baseline"] = verified_ref
        self._write_json(auto_manifest_path, auto_manifest)

        manifest_path = evidence_dir / f"{prefix}-evidence-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["evidence"]["verified_unsafe_baseline"] = verified_ref
        self._write_json(manifest_path, manifest)

        final_path = evidence_dir / f"{prefix}-final-verification.json"
        final = json.loads(final_path.read_text(encoding="utf-8"))
        final["verified_unsafe_baseline"] = verified_ref
        self._write_json(final_path, final)

    def _verified_baseline_same_output_gate_refs_for_tests(
        self,
        evidence_dir: Path,
        prefix: str,
        output_ref: dict,
        compile_ref: dict,
    ) -> dict:
        gate_paths = {
            "c_oracle": (evidence_dir / f"{prefix}-c-oracle-status.json", "C_ORACLE_GENERATED"),
            "rust_replay": (evidence_dir / f"{prefix}-c2rust-direct-replay.json", "passed"),
            "schema_diff": (evidence_dir / f"{prefix}-diff.json", "passed"),
            "negative_diff": (evidence_dir / f"{prefix}-negative-diff.json", "expected_failed"),
            "unsafe_scan": (evidence_dir / f"{prefix}-unsafe-scan.json", "passed"),
            "unsafe_ledger": (evidence_dir / f"{prefix}-unsafe-ledger.json", "passed"),
            "final_verification": (evidence_dir / f"{prefix}-final-verification.json", "passed"),
        }
        refs = {}
        for gate, (path, status) in gate_paths.items():
            ref = self._ref(path, status)
            ref["binding"] = "same_c2rust_output"
            ref["c2rust_output"] = dict(output_ref)
            ref["compile_artifact"] = dict(compile_ref)
            if gate == "rust_replay":
                ref["replay_kind"] = "direct_c2rust_output_replay"
                ref["correctness_role"] = "direct_replay_evidence"
            refs[gate] = ref
        return refs

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
