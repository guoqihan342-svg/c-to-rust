class _AutoMigrateTestsPart08:
    def test_c2rust_verified_baseline_passes_when_same_output_gates_are_bound(self) -> None:
        auto_migrate = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            evidence_dir = Path(tmp) / "evidence"
            evidence_dir.mkdir()
            prefix = "l3-real-fdb-calc-crc32"
            spec = {
                "target_id": "flashdb",
                "slice_id": "real-fdb-calc-crc32",
                "function_name": "fdb_calc_crc32",
                "source_commit": "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
                "fixture_contract": {
                    "path": "validation/l2_slices/fixtures/real-fdb-calc-crc32.json",
                    "hash": "fixture-sha",
                    "observable_outputs": ["return_code"],
                },
            }
            output_path = evidence_dir / f"{prefix}-c2rust-baseline-output.rs"
            output_path.write_text("// combined c2rust output\n", encoding="utf-8")
            compile_artifact = evidence_dir / f"{prefix}-c2rust-baseline-output.rlib"
            compile_artifact.write_text("fake rlib\n", encoding="utf-8")
            c2rust_baseline = {
                "status": "generated",
                "output": {
                    "path": output_path.as_posix(),
                    "status": "generated",
                    "sha256": auto_migrate.sha256(output_path),
                },
                "compile": {
                    "status": "passed",
                    "artifact": {
                        "path": compile_artifact.as_posix(),
                        "status": "compiled",
                        "sha256": auto_migrate.sha256(compile_artifact),
                    },
                },
            }
            for suffix in [
                "c-oracle-status",
                "rust-report",
                "diff",
                "negative-diff",
                "unsafe-scan",
                "unsafe-ledger",
                "final-verification",
            ]:
                (evidence_dir / f"{prefix}-{suffix}.json").write_text(
                    json.dumps({"status": "passed", "semantic_pass": True}),
                    encoding="utf-8",
                )
            direct_replay = {
                "status": "passed",
                "semantic_pass": False,
                "observable_replay_pass": True,
                "replay_kind": "direct_c2rust_output_replay",
                "correctness_role": "direct_replay_evidence",
                "c2rust_output": auto_migrate.c2rust_baseline_output_ref(c2rust_baseline, "generated"),
                "compile_artifact": auto_migrate.c2rust_baseline_compile_artifact_ref(c2rust_baseline),
            }
            direct_replay_path = evidence_dir / f"{prefix}-c2rust-direct-replay.json"
            direct_replay_path.write_text(json.dumps(direct_replay), encoding="utf-8")

            with mock.patch.object(auto_migrate, "emit_c2rust_direct_replay_artifact", return_value=direct_replay):
                verified = auto_migrate.emit_c2rust_verified_unsafe_baseline(
                    spec,
                    evidence_dir,
                    c2rust_baseline,
                    {"status": "refused", "level": "L4"},
                    {"status": "passed", "route_level": "L4"},
                    accepted=None,
                    semantic_pass=True,
                )

            self.assertEqual(verified["status"], "passed")
            self.assertTrue(verified["semantic_pass"])
            self.assertEqual(verified["semantic_claim_source"], "verified_unsafe_baseline_gates")
            self.assertEqual(verified["blocked_reasons"], [])
            same_output_gates = verified["same_output_gate_refs"]
            for gate in [
                "c_oracle",
                "rust_replay",
                "schema_diff",
                "negative_diff",
                "unsafe_scan",
                "unsafe_ledger",
                "final_verification",
            ]:
                self.assertEqual(same_output_gates[gate]["c2rust_output"], verified["c2rust_output"])
            self.assertEqual(
                same_output_gates["rust_replay"]["path"],
                verified["direct_c2rust_replay"]["artifact"]["path"],
            )
            self.assertNotIn("sha256", same_output_gates["final_verification"])
            self.assertEqual(
                same_output_gates["final_verification"]["hash_binding"],
                "omitted_to_avoid_final_verification_verified_baseline_hash_cycle",
            )

    def test_c2rust_baseline_schema_rejects_hollow_generated_manifest(self) -> None:
        schema = json.loads(
            (
                REPO_ROOT
                / "validation"
                / "auto-translation-template"
                / "c2rust-baseline-manifest.schema.json"
            ).read_text(encoding="utf-8")
        )
        generated_manifest = {
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "c2rust-generated",
            "status": "generated",
            "reason": "generated_by_c2rust",
            "correctness_role": "candidate_context_only",
            "fallback_oracle": "original_c_oracle_required",
            "validation_impact": "candidate context only",
            "source_commit": "1234567",
            "slice_spec": {"path": "slice.json", "sha256": "slice-sha"},
            "build_profile_hash": "profile-sha",
            "commands": [
                {
                    "name": "c2rust",
                    "path": "fake-c2rust",
                    "available": True,
                    "version_status": "OK",
                    "version": "c2rust 0.18.0",
                }
            ],
            "selected_command": {"name": "c2rust", "path": "fake-c2rust"},
            "reference_tree": {
                "path": "tools/c2rust-reference",
                "status": "missing",
                "cargo_toml": "",
                "diagnostic_only": True,
            },
            "generation": {
                "enabled": True,
                "enabled_by": "C2RUST_BASELINE_GENERATION",
                "compile_commands": {"path": "compile_commands.json", "sha256": "compile-db-sha"},
                "command": {
                    "argv": ["c2rust", "transpile", "--emit-build-files", "compile_commands.json"],
                    "working_directory": "validation/evidence/demo",
                    "stdout_log": "baseline.stdout.log",
                    "stderr_log": "baseline.stderr.log",
                    "timeout_seconds": 120,
                    "exit_status": "passed",
                    "returncode": 0,
                },
                "generated_files": [{"path": "src/lib.rs", "sha256": "lib-sha"}],
            },
            "output": {"path": "baseline.rs", "status": "generated", "sha256": "output-sha"},
            "compile": None,
            "diagnostics": [],
            "must_not_claim": ["C2Rust output proves semantic equivalence"],
        }

        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(generated_manifest, schema)

        generated_manifest["compile"] = {
            "status": "passed",
            "attempted": True,
            "semantic_pass": False,
            "candidate_output": {"path": "baseline.rs", "status": "generated", "sha256": "output-sha"},
            "command": {
                "argv": ["rustc", "--crate-type", "lib", "baseline.rs"],
                "working_directory": "validation/evidence/demo",
                "stdout_log": "baseline.stdout.log",
                "stderr_log": "baseline.stderr.log",
                "timeout_seconds": 60,
                "exit_status": "passed",
                "returncode": 0,
            },
            "artifact": {"path": "baseline.rlib", "status": "compiled", "sha256": "artifact-sha"},
            "diagnostics": [],
        }
        generated_manifest["output"] = {"path": "baseline.rs", "sha256": "output-sha"}

        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(generated_manifest, schema)

        generated_manifest["output"] = {"path": "baseline.rs", "status": "generated", "sha256": "output-sha"}
        generated_manifest["generation"].pop("generated_files")

        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(generated_manifest, schema)

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

    def test_c2rust_baseline_generated_candidate_binding_carries_output_ref_only(self) -> None:
        auto_migrate = load_auto_migrate_module()
        manifest_ref = {"path": "l3-demo-c2rust-baseline-manifest.json", "status": "generated", "sha256": "abc"}
        output_ref = {
            "path": "validation/evidence/demo/l3-demo-c2rust-baseline-output.rs",
            "status": "generated",
            "sha256": "def",
        }

        binding = auto_migrate.c2rust_baseline_candidate_binding(
            {
                "status": "generated",
                "reason": "generated_by_c2rust",
                "correctness_role": "candidate_context_only",
                "output": output_ref,
            },
            baseline_manifest_ref=manifest_ref,
        )

        self.assertEqual(binding["candidate_id"], "c2rust-baseline")
        self.assertEqual(binding["correctness_role"], "candidate_context_only")
        self.assertEqual(binding["output_ref"], output_ref)
        self.assertFalse(binding["semantic_pass"])
        self.assertFalse(binding["generated_draft_semantic_pass"])
        self.assertEqual(binding["baseline_manifest"], manifest_ref)

    def test_emit_route_decision_carries_generated_c2rust_output_ref(self) -> None:
        auto_migrate = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "route-c2rust",
            "source_commit": "1234567",
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-route-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-route-c2rust"
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

            output = evidence_dir / f"{prefix}-c2rust-baseline-output.rs"
            output.write_text("pub unsafe fn generated() {}\n", encoding="utf-8")
            output_sha = auto_migrate.sha256(output)
            baseline = {
                "status": "generated",
                "reason": "generated_by_c2rust",
                "correctness_role": "candidate_context_only",
                "output": {
                    "path": output.as_posix(),
                    "status": "generated",
                    "sha256": output_sha,
                },
                "compile": {
                    "status": "passed",
                    "attempted": True,
                    "semantic_pass": False,
                },
            }
            (evidence_dir / f"{prefix}-c2rust-baseline-manifest.json").write_text(
                json.dumps(baseline), encoding="utf-8"
            )

            route = auto_migrate.emit_route_decision(spec, evidence_dir, {"status": "generated"}, baseline)

        c2rust_candidate = route["candidate_generation"]["c2rust_baseline"]
        self.assertEqual(c2rust_candidate["status"], "generated")
        self.assertEqual(c2rust_candidate["output_ref"]["sha256"], output_sha)
        self.assertFalse(c2rust_candidate["semantic_pass"])
        self.assertFalse(c2rust_candidate["generated_draft_semantic_pass"])

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
