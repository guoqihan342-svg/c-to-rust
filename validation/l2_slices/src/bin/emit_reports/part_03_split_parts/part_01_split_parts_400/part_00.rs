fn emit_add_i32_pair_ptr_arith_performance_smoke(
    report: &AddI32PairPtrArithOracleReport,
    evidence_dir: &Path,
) -> Result<(), Box<dyn Error>> {
    let iterations = PERFORMANCE_SMOKE_ITERATIONS;
    let mut calls = 0_u64;
    for _ in 0..iterations {
        for case in &report.cases {
            let alias_case =
                add_i32_pair_ptr_arith::AddI32PairAliasCase::from_fixture(&case.alias_case)
                    .ok_or("add_i32_pair_ptr_arith oracle contains unknown alias_case")?;
            let _ =
                add_i32_pair_ptr_arith::add_i32_pair_ptr_arith(&case.lhs, &case.rhs, alias_case);
            calls += 1;
        }
    }
    write_json(
        &evidence_dir.join("l3-add-i32-pair-ptr-arith-performance-smoke.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "add-i32-pair-ptr-arith",
            "source_commit": "demo-add-i32-pair-ptr-arith-20260625",
            "status": "recorded",
            "secondary_only": true,
            "operation": "safe Rust add_i32_pair_ptr_arith replay over fixture corpus",
            "iterations": iterations,
            "calls": calls,
            "elapsed_ms": 0.0,
            "elapsed_boundary": "Deterministic report refresh records call count; wall-clock step duration is recorded by full regression logs.",
            "reporting_boundary": "Performance smoke is secondary evidence only and does not replace correctness gates."
        }),
    )
}

fn emit_store_add_one_translation_evidence(
    evidence_dir: &Path,
    common_obj: &serde_json::Map<String, serde_json::Value>,
    repo_commit: &str,
    case_count: usize,
) -> Result<(), Box<dyn Error>> {
    write_json(
        &evidence_dir.join("l3-store-add-one-pointer-graph.json"),
        &json!({
            "schema_version": common_obj["schema_version"],
            "target_id": common_obj["target_id"],
            "slice_id": common_obj["slice_id"],
            "level": common_obj["level"],
            "status": "recorded",
            "source_commit": common_obj["source_commit"],
            "repo_commit": common_obj["repo_commit"],
            "context_pack_ref": "validation/evidence/demo/l3-store-add-one-context-pack.json",
            "config_profile_ref": "validation/evidence/demo/l3-store-add-one-config-profile.json",
            "applicability": {"has_pointer_surface": true, "triggers": ["pointer_parameter"]},
            "source_boundary": {
                "files": ["validation/l2_slices/tools/generate_store_add_one_oracle.py"],
                "functions": ["store_add_one"],
                "structs": [],
                "globals": [],
                "direct_call_edges": []
            },
            "pointer_nodes": [
                {
                    "id": "out",
                    "symbol": "out",
                    "kind": "raw_pointer",
                    "c_type": "int*",
                    "mutability": "write_only",
                    "nullability": "unknown",
                    "ownership_role": "out_param",
                    "lifetime_owner": "caller",
                    "cross_file_exposure": false,
                    "write_effects": ["out[0]"],
                    "read_effects": [],
                    "boundary_decisions": ["bounded_pointer_index"]
                }
            ],
            "dependency_edges": [
                {"from": "value", "to": "out", "relationship": "writes_through", "evidence": "out[0] = value + 1"}
            ],
            "alias_sets": [],
            "external_state": [],
            "rust_mapping": [
                {
                    "pointer_node": "out",
                    "strategy": "Map C out[0] write to owned StoreAddOneReport.out0 return field.",
                    "unsafe_expected": false
                }
            ],
            "pointer_decisions": [
                {
                    "pointer_node": "out",
                    "decision": "bounded_pointer_index",
                    "index": 0,
                    "write_effect": "out[0]",
                    "unsafe_expected": false
                }
            ],
            "validation_coverage": {
                "fixtures": ["validation/l2_slices/fixtures/store-add-one-c-oracle.json"],
                "tests": ["validation/l2_slices/tests/store_add_one.rs"],
                "oracle_reports": [
                    "validation/evidence/demo/l3-store-add-one-c-oracle.json",
                    "validation/evidence/demo/l3-store-add-one-rust-report.json"
                ]
            },
            "risk_summary": {
                "unsafe_expected": false,
                "blocked_reasons": [],
                "known_gaps": [
                    "NULL out pointer is not executed.",
                    "INT_MAX is excluded because signed C overflow is undefined behavior.",
                    "No aliasing claim."
                ]
            },
            "cache_invalidation_keys": [
                "source_commit",
                "repo_commit",
                "fixture.hash",
                "pointer_nodes",
                "pointer_decisions",
                "schema_version"
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-test-translation.json"),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "store-add-one",
            "level": "L3",
            "status": "recorded",
            "source_commit": "demo-store-add-one-20260625",
            "repo_commit": repo_commit,
            "source_test_inputs": {
                "oracle_strategy": "WSL gcc compiles and runs the C helper, then Rust cargo tests replay the same fixture.",
                "fixtures": [
                    {
                        "path": "validation/l2_slices/fixtures/store-add-one-c-oracle.json",
                        "hash": "store-add-one-fixture",
                        "operation_count": case_count,
                        "source_kind": "fixture"
                    }
                ],
                "oracle_reports": [
                    {"path": "validation/evidence/demo/l3-store-add-one-c-oracle.json", "status": "passed"},
                    {"path": "validation/evidence/demo/l3-store-add-one-rust-report.json", "status": "passed"}
                ]
            },
            "rust_tests": [
                {
                    "file": "validation/l2_slices/tests/store_add_one.rs",
                    "test_names": ["store_add_one_matches_c_oracle_with_safe_boundary"],
                    "cargo_command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test store_add_one",
                    "framework": "cargo test"
                }
            ],
            "coverage": {
                "main_paths": ["negative input", "zero input", "positive input"],
                "error_paths": [],
                "negative_cases": ["out0 mutation rejected by negative diff"]
            },
            "translation_mappings": [
                {
                    "source": "validation/l2_slices/fixtures/store-add-one-c-oracle.json",
                    "rust_test": "validation/l2_slices/tests/store_add_one.rs::store_add_one_matches_c_oracle_with_safe_boundary",
                    "behavior_fields": ["return_code", "status", "out0"],
                    "coverage_kind": "main_path",
                    "status": "mapped"
                },
                {
                    "source": "validation/evidence/demo/l3-store-add-one-negative-diff.json",
                    "rust_test": "validation/l2_slices/src/bin/emit_reports.rs::emit_store_add_one_negative_diff",
                    "behavior_fields": ["out0"],
                    "coverage_kind": "negative_case",
                    "status": "mapped"
                }
            ],
            "evidence_links": {
                "c_oracle": {"path": "validation/evidence/demo/l3-store-add-one-c-oracle.json", "status": "passed"},
                "rust_report": {"path": "validation/evidence/demo/l3-store-add-one-rust-report.json", "status": "passed"},
                "schema_diff": {"path": "validation/evidence/demo/l3-store-add-one-diff.json", "status": "passed"},
                "negative_diff": {"path": "validation/evidence/demo/l3-store-add-one-negative-diff.json", "status": "expected_failed"},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-store-add-one-unsafe-ledger.json", "status": "passed"}
            },
            "known_gaps": [
                "Generated Rust draft remains a candidate; accepted semantics are bound to the checked Rust replay evidence.",
                "No NULL out pointer execution.",
                "No INT_MAX signed overflow case."
            ],
            "cache_invalidation_keys": [
                "schema_version",
                "source_commit",
                "fixture=validation/l2_slices/fixtures/store-add-one-c-oracle.json",
                "cargo test --manifest-path validation/l2_slices/Cargo.toml --test store_add_one"
            ]
        }),
    )?;
    Ok(())
}
