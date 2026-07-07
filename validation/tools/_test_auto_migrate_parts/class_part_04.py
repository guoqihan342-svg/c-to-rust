class _AutoMigrateTestsPart04:
    def test_call_edge_binding_includes_accepted_named_slice_external_callee(self) -> None:
        module = load_auto_migrate_module()
        context = {
            "declared": [
                {
                    "name": "fdb_blob_make",
                    "signature_ref": "sig-fdb-blob-make",
                    "stub_kind": "accepted_named_slice_evidence",
                },
                {
                    "name": "fdb_kv_del",
                    "signature_ref": "sig-fdb-kv-del",
                    "stub_kind": "compile_only",
                },
            ]
        }
        call_expressions = [
            {
                "callee": "fdb_blob_make",
                "source_expression": "fdb_blob_make(&blob, value, strlen(value))",
                "statement_context": "return:arg2",
            },
            {
                "callee": "fdb_kv_del",
                "source_expression": "fdb_kv_del(db, key)",
                "statement_context": "return:value",
            },
        ]

        bindings = module.call_edge_to_callee_binding(call_expressions, context)

        self.assertEqual(
            [(item["callee"], item["stub_kind"]) for item in bindings],
            [
                ("fdb_blob_make", "accepted_named_slice_evidence"),
                ("fdb_kv_del", "compile_only"),
            ],
        )
        self.assertFalse(any(item["semantics_verified"] for item in bindings))

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
            evidence_dir = out_root / "demo" / "auto-translation" / "fill-first"
            cfg = json.loads((evidence_dir / "l3-fill-first-cfg.json").read_text(encoding="utf-8"))
            pointer_graph = json.loads((evidence_dir / "l3-fill-first-pointer-graph.json").read_text(encoding="utf-8"))
            plan = json.loads((evidence_dir / "l3-fill-first-auto-translation-plan.json").read_text(encoding="utf-8"))
            block = cfg["functions"][0]["basic_blocks"][0]

            _, plan = self._assert_route_refused_candidate(manifest, evidence_dir, "fill-first")
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
            evidence_dir = out_root / "demo" / "auto-translation" / "sum-i32-buffer"
            cfg = json.loads((evidence_dir / "l3-sum-i32-buffer-cfg.json").read_text(encoding="utf-8"))
            pointer_graph = json.loads(
                (evidence_dir / "l3-sum-i32-buffer-pointer-graph.json").read_text(encoding="utf-8")
            )
            plan = json.loads(
                (evidence_dir / "l3-sum-i32-buffer-auto-translation-plan.json").read_text(encoding="utf-8")
            )
            block = cfg["functions"][0]["basic_blocks"][0]

            _, plan = self._assert_route_refused_candidate(manifest, evidence_dir, "sum-i32-buffer")
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

            _, plan = self._assert_route_refused_candidate(manifest, evidence_dir, "sum-i32-ptr-arith")
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

            _, plan = self._assert_route_refused_candidate(manifest, evidence_dir, "fill-i32-ptr-arith-out")
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
