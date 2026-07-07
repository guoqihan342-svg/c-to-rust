class _AutoMigrateTestsPart03:
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
                    sys.executable,
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
            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            self._assert_route_refused_candidate(manifest, evidence_dir, "adler32-step")
            self.assertEqual(manifest["source_commit"], "d40f29fd42ed9158e3eb3e221dca50e4b627f7a8")
            self.assertEqual(manifest["fixture"]["hash"], "zlib-adler32-fixture")
            self.assertEqual(manifest["oracle"]["status"], "SKIPPED_LOCAL_NO_C_TOOLCHAIN")
            self.assertEqual(manifest["oracle"]["fixture"], "validation/l2_slices/fixtures/zlib-adler32-c-oracle.json")
            self.assertEqual(manifest["replay"]["fixture"], "validation/l2_slices/fixtures/zlib-adler32-c-oracle.json")
            self.assertTrue(
                (evidence_dir / "l3-adler32-step-type-map.json").exists()
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
            evidence_dir = out_root / "demo" / "auto-translation" / "compound-inc-dec"
            draft = (evidence_dir / "l3-compound-inc-dec-rust-draft.rs").read_text(encoding="utf-8")
            plan = json.loads(
                (evidence_dir / "l3-compound-inc-dec-auto-translation-plan.json").read_text(encoding="utf-8")
            )
            cfg = json.loads((evidence_dir / "l3-compound-inc-dec-cfg.json").read_text(encoding="utf-8"))
            statement_kinds = cfg["functions"][0]["basic_blocks"][0]["statement_kinds"]

            _, plan = self._assert_route_refused_candidate(manifest, evidence_dir, "compound-inc-dec")
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

            _, plan = self._assert_route_refused_candidate(manifest, evidence_dir, "call-expression")
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

    def test_real_fdb_kv_set_rust_check_uses_harness_only_external_bindings(self) -> None:
        module = load_auto_migrate_module()
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-kv-set.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        real_draft = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "flashdb"
            / "auto-translation"
            / "real-fdb-kv-set"
            / "l3-real-fdb-kv-set-rust-draft.rs"
        ).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="auto-migrate-real-fdb-kv-set-rust-check-") as tmp:
            draft_path = Path(tmp) / "l3-real-fdb-kv-set-rust-draft.rs"
            draft_path.write_text(real_draft, encoding="utf-8")
            context = module.external_direct_callee_context(spec, None)

            changed = module.inject_external_callee_stubs(draft_path, context)
            rust_check = module.rust_check_once(draft_path)
            claim_scope = module.external_callee_claim_scope(context)
            reported_context = module.rust_check_external_context(context)

            self.assertTrue(changed)
            self.assertEqual(rust_check["returncode"], 0, rust_check["stderr"])
            draft = draft_path.read_text(encoding="utf-8")
            self.assertIn("rust-check harness-only external callee binding: fdb_blob_make", draft)
            self.assertIn(
                "pub fn fdb_blob_make(blob: &mut FdbBlob, value_buf: *const core::ffi::c_void, buf_len: usize) -> &mut FdbBlob",
                draft,
            )
            self.assertIn(
                "pub fn fdb_kv_set_blob(db: *mut core::ffi::c_void, key: *const core::ffi::c_void, blob: &mut FdbBlob) -> i32",
                draft,
            )
            self.assertIn(
                "pub fn fdb_kv_del(db: *mut core::ffi::c_void, key: *const core::ffi::c_void) -> i32",
                draft,
            )
            self.assertNotIn("fn strlen", draft)
            self.assertEqual(claim_scope["status"], "compile_context_only")
            self.assertFalse(claim_scope["semantics_verified"])
            self.assertFalse(
                module.semantic_pass_for_run(
                    None,
                    {"status": "passed"},
                    {"status": "blocked", "generated_draft_semantic_pass": False},
                )
            )
            bindings = {
                item["name"]: item
                for item in reported_context["declared_callees"]
            }
            self.assertEqual(bindings["fdb_blob_make"]["binding_status"], "harness_only")
            self.assertEqual(bindings["fdb_kv_set_blob"]["binding_status"], "harness_only")
            self.assertEqual(bindings["fdb_kv_del"]["binding_status"], "harness_only")
            self.assertFalse(bindings["fdb_blob_make"]["semantics_verified"])
            self.assertFalse(bindings["fdb_kv_set_blob"]["semantics_verified"])
            self.assertFalse(bindings["fdb_kv_del"]["semantics_verified"])
            replay = {
                "schema_version": 1,
                "status": "skipped",
                "generated_draft_replay_pass": False,
                "generated_draft_semantic_pass": False,
            }
            skipped_replay = module.run_generated_rust_replay(
                spec,
                Path(tmp),
                replay,
                {
                    "status": "passed",
                    "rust_check_harness_only_bindings": module.rust_check_external_binding_report(context),
                },
            )
            self.assertEqual(skipped_replay["status"], "not_applicable")
            self.assertEqual(
                skipped_replay["skip_reason"],
                "compile_only_external_bindings_not_executable",
            )
            self.assertEqual(
                skipped_replay["not_applicable_reason"],
                "compile_only_external_bindings_not_executable",
            )
            self.assertFalse(skipped_replay["generated_draft_semantic_pass"])
