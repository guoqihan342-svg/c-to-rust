class _AutoMigrateTestsPart06:
    def test_keyword_identifier_self_healing_stops_after_five_repair_rounds(self) -> None:
        module = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "six-keyword-param",
            "source_commit": "1234567",
            "function_name": "six_keyword_param",
            "fixture_hash": "fixture",
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            draft_path = evidence_dir / "l3-six-keyword-param-rust-draft.rs"
            draft_path.write_text(
                "\n".join(
                    [
                        "pub fn six_keyword_param("
                        "match: i32, type: i32, loop: i32, move: i32, async: i32, while: i32"
                        ") -> i32 {",
                        "    match + type + loop + move + async + while",
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            rust_check, patch = module.run_rust_check(evidence_dir, False, spec)

            self.assertEqual(rust_check["status"], "failed")
            self.assertEqual(patch["status"], "blocked")
            self.assertTrue(patch["self_heal_applied"])
            events = [
                json.loads(line)
                for line in (evidence_dir / "l3-six-keyword-param-patch-events.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            self.assertEqual(
                [event["round"] for event in events if event["status"] == "applied"],
                [1, 2, 3, 4, 5],
            )
            self.assertEqual(events[-1]["status"], "blocked")
            self.assertEqual(events[-1]["round"], 5)
            self.assertEqual(events[-1]["patch_id"], "patch-blocked-5")
            draft = draft_path.read_text(encoding="utf-8")
            for name in ("match", "type", "loop", "move", "async"):
                self.assertIn(f"r#{name}", draft)
            self.assertIn("while: i32", draft)

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
                    sys.executable,
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
                    sys.executable,
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

    def test_real_fdb_calc_crc32_clang_typed_ir_unavailable_refuses_candidate_route(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            out_root = Path(tmp) / "evidence"
            result = subprocess.run(
                [
                    sys.executable,
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

            route, plan = self._assert_route_refused_candidate(
                manifest,
                evidence_dir,
                "real-fdb-calc-crc32",
            )
            self.assertEqual(
                plan["translation_source"],
                {
                    "selected": "legacy-string-translator",
                    "fallback_from": "clang-lowered-typed-ir",
                    "fallback_reason": "clang_lowered_typed_ir_unavailable",
                },
            )
            self.assertEqual(pointer["status"], "not_applicable")
            self.assertFalse(pointer["applicability"]["has_pointer_surface"])
            self.assertEqual(pointer["not_applicable_reason"], "slice has no pointer surface")
            self.assertEqual(plan["translation_summary"]["unsupported_node_count"], 2)
            self.assertEqual(rust_check["status"], "passed")

    def test_real_fdb_calc_crc32_translator_input_records_real_tu_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            slice_spec = json.loads(
                (REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-calc-crc32.json").read_text(
                    encoding="utf-8"
                )
            )
            out_root = Path(tmp) / "evidence"
            result = subprocess.run(
                [
                    sys.executable,
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
                slice_spec["source"]["source_root"],
            )
            self.assertEqual(translator_input["source_file"], "src/fdb_utils.c")
            self.assertEqual(
                translator_input["source_file_hashes"],
                {
                    "src/fdb_utils.c": (
                        "bb6d6bdf60d5176be307273f61bf1040b2bad668b018af612e026a58637d49c0"
                    )
                },
            )
            self.assertEqual(
                translator_input["source_files"],
                [
                    {
                        "path": "src/fdb_utils.c",
                        "role": "source",
                        "sha256": "bb6d6bdf60d5176be307273f61bf1040b2bad668b018af612e026a58637d49c0",
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
                slice_spec["build_profile"]["compiler_command_source"],
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
            rust_draft_sha = module.sha256(draft_path)
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
