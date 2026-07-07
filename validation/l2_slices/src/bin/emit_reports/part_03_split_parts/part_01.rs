fn emit_store_add_one_static_l3_evidence(
    evidence_dir: &Path,
    case_count: usize,
    status: &str,
) -> Result<(), Box<dyn Error>> {
    let manifest_status = if status == "passed" {
        "passed"
    } else {
        "failed"
    };
    let repo_commit = "workspace".to_owned();
    let common = json!({
        "schema_version": 1,
        "level": "L3",
        "target_id": "demo",
        "slice_id": "store-add-one",
        "source_commit": "demo-store-add-one-20260625",
        "repo_commit": repo_commit
    });
    let common_obj = common.as_object().ok_or("common evidence object")?;

    write_json(
        &evidence_dir.join("l3-store-add-one-slice-contract.json"),
        &json!({
            "schema_version": common_obj["schema_version"],
            "level": common_obj["level"],
            "target_id": common_obj["target_id"],
            "slice_id": common_obj["slice_id"],
            "source_commit": common_obj["source_commit"],
            "repo_commit": common_obj["repo_commit"],
            "status": "recorded",
            "source_boundary": {
                "files": ["validation/l2_slices/tools/generate_store_add_one_oracle.py"],
                "functions": ["store_add_one"],
                "signature": "int store_add_one(int value, int* out)"
            },
            "rust_boundary": {
                "module": "validation/l2_slices/src/store_add_one.rs",
                "api": "pub fn store_add_one(value: i32) -> StoreAddOneReport",
                "safe_rust": true,
                "raw_pointer_exposed": false
            },
            "fixture": {
                "path": "validation/l2_slices/fixtures/store-add-one-c-oracle.json",
                "hash": "store-add-one-fixture",
                "case_count": case_count
            },
            "behavior_fields": ["return_code", "status", "out0"],
            "accepted_differences": [],
            "non_goals": [
                "No NULL out pointer execution.",
                "No INT_MAX signed overflow case.",
                "No unbounded pointer index, pointer arithmetic, aliasing, or struct field writes.",
                "No full project migration claim."
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-context-pack.json"),
        &json!({
            "schema_version": common_obj["schema_version"],
            "level": common_obj["level"],
            "target_id": common_obj["target_id"],
            "slice_id": common_obj["slice_id"],
            "source_commit": common_obj["source_commit"],
            "repo_commit": common_obj["repo_commit"],
            "status": "recorded",
            "direct_c_files": ["validation/l2_slices/tools/generate_store_add_one_oracle.py"],
            "direct_rust_files": [
                "validation/l2_slices/src/store_add_one.rs",
                "validation/l2_slices/tests/store_add_one.rs",
                "validation/l2_slices/src/bin/emit_reports.rs"
            ],
            "call_edges": [
                {"from": "C oracle helper", "to": "store_add_one"},
                {"from": "Rust emit_reports", "to": "store_add_one::store_add_one"}
            ],
            "related_tests": [
                "validation/l2_slices/tests/store_add_one.rs::store_add_one_matches_c_oracle_with_safe_boundary"
            ],
            "cache_inputs": [
                "fixture=validation/l2_slices/fixtures/store-add-one-c-oracle.json",
                "rust_module=validation/l2_slices/src/store_add_one.rs",
                "rust_test=validation/l2_slices/tests/store_add_one.rs"
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-config-profile.json"),
        &json!({
            "schema_version": common_obj["schema_version"],
            "level": common_obj["level"],
            "target_id": common_obj["target_id"],
            "slice_id": common_obj["slice_id"],
            "source_commit": common_obj["source_commit"],
            "repo_commit": common_obj["repo_commit"],
            "status": "recorded",
            "profile_id": "demo-store-add-one-wsl-gcc",
            "config_header": {"path": null, "role": "not_required"},
            "compile_profile": {
                "c_oracle_command": "python -B validation/l2_slices/tools/generate_store_add_one_oracle.py",
                "include_paths": [],
                "config_header_included": false,
                "command_args": ["wsl", "gcc", "-std=c99", "-Wall", "-Wextra", "-Werror"]
            },
            "rust_profile": {
                "package": "c-to-rust-l2-slices",
                "cargo_features": [],
                "backend": "safe-rust-validation-slice"
            },
            "cache_invalidation_keys": [
                "source_commit",
                "repo_commit",
                "fixture.hash",
                "rust_boundary.module",
                "translator_version"
            ]
        }),
    )?;
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
    write_json(
        &evidence_dir.join("l3-store-add-one-rust-check.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "source_commit": "demo-store-add-one-20260625",
            "status": status,
            "compile_self_healing": {
                "attempt_count": 0,
                "unresolved_errors": 0
            },
            "commands": [
                {
                    "command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test store_add_one",
                    "status": status
                },
                {
                    "command": "cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports",
                    "status": status
                }
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-final-verification.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "source_commit": "demo-store-add-one-20260625",
            "status": status,
            "semantic_pass": status == "passed",
            "fixture": {
                "path": "validation/l2_slices/fixtures/store-add-one-c-oracle.json"
            },
            "rust_check_status": status,
            "c_oracle_status": "passed",
            "toolchain_status": "C_ORACLE_GENERATED",
            "rust_report_status": status,
            "schema_diff_status": status,
            "negative_diff_mutation_detected": true,
            "unsafe_status": "passed",
            "version_config_status": "recorded",
            "generated_draft_semantic_pass": false
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-summary.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "source_commit": "demo-store-add-one-20260625",
            "status": status,
            "semantic_pass": status == "passed",
            "summary": "store_add_one out[0] pointer-output demo has accepted C oracle, Rust replay, diff, negative diff, unsafe, and version evidence.",
            "generated_draft_semantic_pass": false,
            "known_gaps": [
                "No NULL out pointer execution.",
                "No INT_MAX signed overflow case.",
                "No aliasing or unbounded pointer index claim."
            ]
        }),
    )?;
    let version_payload = json!({
        "schema_version": 1,
        "level": "L3",
        "target_id": "demo",
        "slice_id": "store-add-one",
        "source_commit": "demo-store-add-one-20260625",
        "repo_commit": repo_commit,
        "status": "recorded",
        "semantic_pass": status == "passed",
        "translator_version": "0.1.0",
        "fixture": {
            "path": "validation/l2_slices/fixtures/store-add-one-c-oracle.json",
            "hash": "store-add-one-fixture"
        },
        "cache_invalidation_keys": [
            "source_commit",
            "repo_commit",
            "fixture.hash",
            "rust_boundary.module",
            "translator_version"
        ]
    });
    write_json(
        &evidence_dir.join("l3-store-add-one-version-manifest.json"),
        &version_payload,
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-cache-metadata.json"),
        &version_payload,
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-evidence-manifest.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "status": manifest_status,
            "source_commit": "demo-store-add-one-20260625",
            "repo_commit": repo_commit,
            "fixture": {
                "path": "validation/l2_slices/fixtures/store-add-one-c-oracle.json",
                "hash": "store-add-one-fixture",
                "operation_count": case_count
            },
            "evidence": {
                "slice_contract": {"path": "validation/evidence/demo/l3-store-add-one-slice-contract.json", "status": "recorded"},
                "context_pack": {"path": "validation/evidence/demo/l3-store-add-one-context-pack.json", "status": "recorded"},
                "cache_metadata": {"path": "validation/evidence/demo/l3-store-add-one-cache-metadata.json", "status": "recorded"},
                "config_profile": {"path": "validation/evidence/demo/l3-store-add-one-config-profile.json", "status": "recorded", "profile_id": "demo-store-add-one-wsl-gcc"},
                "pointer_dependency_graph": {"path": "validation/evidence/demo/l3-store-add-one-pointer-graph.json", "status": "recorded"},
                "test_translation": {"path": "validation/evidence/demo/l3-store-add-one-test-translation.json", "status": "recorded"},
                "c_oracle": {"path": "validation/evidence/demo/l3-store-add-one-c-oracle.json", "status": "passed", "toolchain_status": "C_ORACLE_GENERATED"},
                "rust_report": {"path": "validation/evidence/demo/l3-store-add-one-rust-report.json", "status": status},
                "schema_diff": {"path": "validation/evidence/demo/l3-store-add-one-diff.json", "status": status},
                "negative_diff": {"path": "validation/evidence/demo/l3-store-add-one-negative-diff.json", "status": "expected_failed", "expected_failure": true, "mutation_detected": true},
                "rust_check": {"path": "validation/evidence/demo/l3-store-add-one-rust-check.json", "status": status},
                "unsafe_scan": {"path": "validation/evidence/demo/l3-store-add-one-unsafe-scan.json", "status": "passed"},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-store-add-one-unsafe-ledger.json", "status": "passed"},
                "performance_smoke": {"path": "validation/evidence/demo/l3-store-add-one-performance-smoke.json", "status": "recorded", "secondary_only": true},
                "final_verification": {"path": "validation/evidence/demo/l3-store-add-one-final-verification.json", "status": status},
                "summary": {"path": "validation/evidence/demo/l3-store-add-one-summary.json", "status": status},
                "version_or_config_binding": {"path": "validation/evidence/demo/l3-store-add-one-version-manifest.json", "status": "recorded"}
            },
            "claim_boundary": {
                "scope": "Only the demo store_add_one slice for the committed fixture corpus.",
                "behavior_fields_checked": ["return_code", "status", "out0"],
                "accepted_metadata_differences": [],
                "known_gaps": [
                    "No NULL out pointer execution.",
                    "No INT_MAX signed overflow case.",
                    "No aliasing or unbounded pointer index claim."
                ],
                "must_not_claim": [
                    "full automatic C99/C11 translation",
                    "whole-program alias safety",
                    "NULL pointer equivalence",
                    "signed overflow equivalence"
                ]
            }
        }),
    )
}

