class _AutoMigrateTestsPart05:
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
                    sys.executable,
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
                    sys.executable,
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
            verified_baseline_path = evidence_dir / "l3-unbounded-authoritative-c2rust-verified-unsafe-baseline.json"
            auto_manifest = json.loads(
                (evidence_dir / "l3-unbounded-authoritative-auto-translation-manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            evidence_manifest = json.loads(
                (evidence_dir / "l3-unbounded-authoritative-evidence-manifest.json").read_text(encoding="utf-8")
            )

            self.assertEqual(manifest["status"], "accepted_evidence_bound")
            self.assertTrue(manifest["semantic_pass"])
            self.assertTrue(verified_baseline_path.exists())
            verified_baseline = json.loads(verified_baseline_path.read_text(encoding="utf-8"))
            self.assertEqual(verified_baseline["status"], "blocked")
            self.assertFalse(verified_baseline["semantic_pass"])
            self.assertEqual(verified_baseline["semantic_claim_source"], "blocked_missing_direct_c2rust_replay")
            self.assertTrue(
                auto_manifest["verified_unsafe_baseline"]["path"].endswith(
                    "l3-unbounded-authoritative-c2rust-verified-unsafe-baseline.json"
                )
            )
            self.assertEqual(
                auto_manifest["verified_unsafe_baseline"]["sha256"],
                hashlib.sha256(verified_baseline_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(auto_manifest["verified_unsafe_baseline"], evidence_manifest["evidence"]["verified_unsafe_baseline"])
            self.assertEqual(final["verified_unsafe_baseline"], auto_manifest["verified_unsafe_baseline"])
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
                    sys.executable,
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
                    sys.executable,
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

    def test_route_refused_compile_failure_records_blocked_patch_evidence(self) -> None:
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
            evidence_dir = out_root / "demo" / "auto-translation" / "bad-syntax"
            self._assert_route_refused_candidate(
                manifest,
                evidence_dir,
                "bad-syntax",
                rust_status="failed",
            )
            self.assertEqual(manifest["rust_check"]["status"], "failed")
            self.assertEqual(manifest["patch"]["status"], "blocked")
            blocked_path = evidence_dir / "l3-bad-syntax-self-healing-blocked-repairs.json"
            blocked = json.loads(blocked_path.read_text(encoding="utf-8"))
            self.assertEqual(blocked["status"], "recorded")
            repair = blocked["blocked_repairs"][0]
            self.assertEqual(repair["candidate_patch_id"], "patch-route-refused-1")
            self.assertTrue(repair["human_action_required"])
            self.assertEqual(repair["ir_feature_gap"]["kind"], "blocked_artifact")
            self.assertEqual(repair["oracle_fixture_gap"]["status"], "not_blocking")
            self.assertEqual(repair["smallest_next_test"]["kind"], "route_refusal_regression")
            self.assertIn("human_intervention_point", repair)

    def test_keyword_identifier_diagnostic_draft_is_self_healed_but_route_refused(self) -> None:
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
            evidence_dir = out_root / "demo" / "auto-translation" / "keyword-param"
            self._assert_route_refused_candidate(manifest, evidence_dir, "keyword-param")
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertEqual(manifest["patch"]["status"], "blocked")
            patch_events = (
                evidence_dir / "l3-keyword-param-patch-events.jsonl"
            ).read_text(encoding="utf-8")
            self.assertIn('"patch_id": "patch-route-refused-1"', patch_events)
            self.assertIn('"status": "blocked"', patch_events)
            draft = (evidence_dir / "l3-keyword-param-rust-draft.rs").read_text(encoding="utf-8")
            self.assertIn("r#match", draft)

    def test_keyword_identifier_self_healing_uses_five_repair_rounds(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "five-keyword-param",
            "source_commit": "1234567",
            "function_name": "five_keyword_param",
            "fixture_hash": "fixture",
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            draft_path = evidence_dir / "l3-five-keyword-param-rust-draft.rs"
            draft_path.write_text(
                "\n".join(
                    [
                        "pub fn five_keyword_param("
                        "match: i32, type: i32, loop: i32, move: i32, async: i32"
                        ") -> i32 {",
                        "    match + type + loop + move + async",
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            rust_check, patch = module.run_rust_check(evidence_dir, False, spec)

            self.assertEqual(rust_check["status"], "passed", rust_check["errors"])
            self.assertEqual(patch["status"], "recorded")
            self.assertTrue(patch["self_heal_applied"])
            events = [
                json.loads(line)
                for line in (evidence_dir / "l3-five-keyword-param-patch-events.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            self.assertEqual(
                [event["round"] for event in events if event["status"] == "applied"],
                [1, 2, 3, 4, 5],
            )
            self.assertEqual(events[-1]["status"], "verified")
            self.assertEqual(events[-1]["round"], 5)
            draft = draft_path.read_text(encoding="utf-8")
            for name in ("match", "type", "loop", "move", "async"):
                self.assertIn(f"r#{name}", draft)
