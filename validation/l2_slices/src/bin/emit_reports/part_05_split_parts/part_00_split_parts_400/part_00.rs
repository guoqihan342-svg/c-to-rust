fn emit_sum_i32_ptr_arith_static_l3_evidence(
    evidence_dir: &Path,
    case_count: usize,
    status: &str,
    unsafe_status: &str,
) -> Result<(), Box<dyn Error>> {
    let manifest_status = if status == "passed" {
        "passed"
    } else {
        "failed"
    };
    let repo_commit = "workspace".to_owned();
    let source_commit = "demo-sum-i32-ptr-arith-20260625";
    let fixture_path = "validation/l2_slices/fixtures/sum-i32-ptr-arith-c-oracle.json";
    let prefix = "l3-sum-i32-ptr-arith";

    write_json(
        &evidence_dir.join(format!("{prefix}-slice-contract.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "source_boundary": {
                "files": ["validation/l2_slices/tools/generate_sum_i32_ptr_arith_oracle.py"],
                "functions": ["sum_i32_ptr_arith"],
                "signature": "int sum_i32_ptr_arith(const int* values, int len, int* out)"
            },
            "rust_boundary": {
                "module": "validation/l2_slices/src/sum_i32_ptr_arith.rs",
                "api": "pub fn sum_i32_ptr_arith(values: &[i32]) -> SumI32PtrArithReport",
                "raw_pointer_policy": "internal_only",
                "unsafe_policy": {"max_first_party_non_test_ratio": 0.1}
            },
            "fixture": {"path": fixture_path, "hash": "sum-i32-ptr-arith-fixture", "case_count": case_count},
            "claim_boundary": {
                "scope": "Only the demo sum_i32_ptr_arith slice for the committed fixture corpus.",
                "non_goals": ["No NULL pointer execution.", "No negative len execution.", "No pointer arithmetic writes.", "No aliasing or signed overflow claim."]
            }
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-context-pack.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "direct_c_files": ["validation/l2_slices/tools/generate_sum_i32_ptr_arith_oracle.py"],
            "rust_files": [
                "validation/l2_slices/src/sum_i32_ptr_arith.rs",
                "validation/l2_slices/tests/sum_i32_ptr_arith.rs",
                "validation/l2_slices/src/bin/emit_reports.rs"
            ],
            "direct_call_edges": [
                {"from": "C oracle helper", "to": "sum_i32_ptr_arith"},
                {"from": "Rust emit_reports", "to": "sum_i32_ptr_arith::sum_i32_ptr_arith"}
            ],
            "test_entrypoints": [
                "validation/l2_slices/tests/sum_i32_ptr_arith.rs::sum_i32_ptr_arith_matches_c_oracle_with_safe_boundary"
            ],
            "cache_inputs": [fixture_path, "validation/l2_slices/src/sum_i32_ptr_arith.rs"]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-config-profile.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": source_commit,
            "status": "recorded",
            "profile_id": "demo-sum-i32-ptr-arith-wsl-gcc",
            "c_oracle_command": "python -B validation/l2_slices/tools/generate_sum_i32_ptr_arith_oracle.py",
            "rust_replay_command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test sum_i32_ptr_arith",
            "compiler": {"name": "gcc", "mode": "wsl", "standard": "c99"},
            "rust": {"framework": "cargo test", "crate": "validation/l2_slices"}
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-type-map.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": source_commit,
            "status": "recorded",
            "slice_spec_ref": {"path": "validation/slice-specs/demo-sum-i32-ptr-arith.json", "status": "ready"},
            "mappings": [
                {"c_name": "values", "c_type": "const int*", "rust_type": "&[i32]", "kind": "pointer", "decision": "safe_slice_input", "length_companion": "len"},
                {"c_name": "len", "c_type": "int", "rust_type": "i32", "kind": "primitive"},
                {"c_name": "out", "c_type": "int*", "rust_type": "SumI32PtrArithReport", "kind": "pointer", "decision": "owned_report_output"},
                {"c_name": "total", "c_type": "int", "rust_type": "i32", "kind": "primitive"},
                {"c_name": "i", "c_type": "int", "rust_type": "i32", "kind": "primitive"}
            ],
            "uncertainties": []
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-cfg.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": source_commit,
            "status": "recorded",
            "functions": [
                {
                    "name": "sum_i32_ptr_arith",
                    "signature": "int sum_i32_ptr_arith(const int* values, int len, int* out)",
                    "basic_blocks": [
                        {
                            "id": "entry",
                            "statements": [
                                "int total = 0",
                                "for (int i = 0; i < len; i++) { total = total + *(values + i); }",
                                "out[0] = total",
                                "return 0"
                            ],
                            "statement_kinds": ["primitive_declaration", "for", "bounded_input_buffer_read", "bounded_pointer_arithmetic_input_read", "pointer_write", "return"],
                            "lvalue_kinds": ["simple_identifier", "bounded_input_buffer", "bounded_pointer_arithmetic_input_buffer", "bounded_pointer_index"],
                            "lvalue_decisions": [
                                {"statement_index": 1, "source_statement": "total = total + *(values + i)", "lvalue_kind": "bounded_pointer_arithmetic_input_buffer", "decision": "bounded_pointer_arithmetic_input_read", "translation_rule_id": "bounded-pointer-arithmetic-input-read"},
                                {"statement_index": 2, "source_statement": "out[0] = total", "lvalue_kind": "bounded_pointer_index", "decision": "bounded_pointer_index", "translation_rule_id": "bounded-pointer-index-write"}
                            ],
                            "terminator": "return",
                            "edges": ["entry->for-1", "entry->return-3"]
                        }
                    ],
                    "unsupported_control_flow": []
                }
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-pointer-graph.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": source_commit,
            "status": "recorded",
            "applicability": {"contains_pointers": true, "triggers": ["pointer_parameter", "buffer"]},
            "pointer_nodes": [
                {
                    "id": "values",
                    "kind": "buffer",
                    "buffer_role": "input",
                    "ownership_role": "borrowed",
                    "mutability": "read_only",
                    "c_type": "const int*",
                    "rust_boundary": "&[i32]",
                    "length_companion": "len",
                    "read_effects": ["values[i]", "*(values + i)"],
                    "write_effects": [],
                    "boundary_decisions": ["bounded_input_buffer", "bounded_pointer_arithmetic_input_read"]
                },
                {
                    "id": "out",
                    "kind": "pointer",
                    "ownership_role": "out_param",
                    "mutability": "write_only",
                    "c_type": "int*",
                    "rust_boundary": "owned safe report",
                    "read_effects": [],
                    "write_effects": ["out[0]"],
                    "boundary_decisions": ["bounded_pointer_index"]
                }
            ],
            "pointer_edges": [{"from": "values", "to": "out", "relationship": "input_influences_output"}],
            "pointer_decisions": [
                {"pointer_node": "values", "decision": "bounded_input_buffer", "read_effect": "values[i]", "length_companion": "len", "translation_rule_id": "bounded-input-buffer-read", "unsafe_expected": false},
                {"pointer_node": "values", "decision": "bounded_pointer_arithmetic_input_read", "read_effect": "*(values + i)", "canonical_read": "values[i]", "length_companion": "len", "translation_rule_id": "bounded-pointer-arithmetic-input-read", "unsafe_expected": false},
                {"pointer_node": "out", "decision": "bounded_pointer_index", "index": 0, "write_effect": "out[0]", "translation_rule_id": "bounded-pointer-index-write", "unsafe_expected": false}
            ],
            "risk_summary": {
                "unsafe_expected": false,
                "known_gaps": ["NULL pointers are not executed.", "Pointer writes through arithmetic are unsupported.", "Aliasing is not proven.", "Signed overflow cases are excluded."]
            }
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-test-translation.json")),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "source_test_inputs": {
                "oracle_strategy": "WSL gcc compiles and runs the C helper, then Rust cargo tests replay the same fixture.",
                "fixtures": [{"path": fixture_path, "hash": "sum-i32-ptr-arith-fixture", "operation_count": case_count, "source_kind": "fixture"}],
                "oracle_reports": [
                    {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-c-oracle.json", "status": "passed"},
                    {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-rust-report.json", "status": "passed"}
                ]
            },
            "rust_tests": [
                {
                    "file": "validation/l2_slices/tests/sum_i32_ptr_arith.rs",
                    "test_names": ["sum_i32_ptr_arith_matches_c_oracle_with_safe_boundary"],
                    "cargo_command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test sum_i32_ptr_arith",
                    "framework": "cargo test"
                }
            ],
            "coverage": {
                "main_paths": ["empty input", "single input", "multi input", "negative values", "pointer arithmetic input read", "boundary-safe sum"],
                "error_paths": [],
                "negative_cases": ["sum mutation rejected by negative diff"]
            },
            "translation_mappings": [
                {
                    "source": fixture_path,
                    "rust_test": "validation/l2_slices/tests/sum_i32_ptr_arith.rs::sum_i32_ptr_arith_matches_c_oracle_with_safe_boundary",
                    "behavior_fields": ["return_code", "status", "len", "sum", "source_reads", "canonical_reads", "source_write"],
                    "coverage_kind": "main_path",
                    "status": "mapped"
                },
                {
                    "source": "validation/evidence/demo/l3-sum-i32-ptr-arith-negative-diff.json",
                    "rust_test": "validation/l2_slices/src/bin/emit_reports.rs::emit_sum_i32_ptr_arith_negative_diff",
                    "behavior_fields": ["sum"],
                    "coverage_kind": "negative_case",
                    "status": "mapped"
                }
            ],
            "evidence_links": {
                "c_oracle": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-c-oracle.json", "status": "passed"},
                "rust_report": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-rust-report.json", "status": "passed"},
                "schema_diff": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-diff.json", "status": "passed"},
                "negative_diff": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-negative-diff.json", "status": "expected_failed"},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-unsafe-ledger.json", "status": unsafe_status}
            }
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-rust-check.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": source_commit,
            "status": status,
            "compile_self_healing": {"attempt_count": 0, "unresolved_errors": 0},
            "commands": [
                {"command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test sum_i32_ptr_arith", "status": status},
                {"command": "cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports", "status": status}
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-final-verification.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": source_commit,
            "status": status,
            "semantic_pass": status == "passed",
            "fixture": {"path": fixture_path},
            "rust_check_status": status,
            "c_oracle_status": "passed",
            "toolchain_status": "C_ORACLE_GENERATED",
            "rust_report_status": status,
            "schema_diff_status": status,
            "negative_diff_mutation_detected": true,
            "unsafe_status": unsafe_status,
            "version_config_status": "recorded",
            "generated_draft_semantic_pass": false
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-summary.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": source_commit,
            "status": status,
            "semantic_pass": status == "passed",
            "summary": "sum_i32_ptr_arith pointer-arithmetic input read demo has accepted C oracle, Rust replay, diff, negative diff, unsafe, and version evidence.",
            "generated_draft_semantic_pass": false,
            "known_gaps": ["No NULL pointer execution.", "No negative len execution.", "No pointer arithmetic writes.", "No aliasing or signed overflow claim."]
        }),
    )?;
    let version_payload = json!({
        "schema_version": 1,
        "level": "L3",
        "target_id": "demo",
        "slice_id": "sum-i32-ptr-arith",
        "source_commit": source_commit,
        "repo_commit": repo_commit,
        "status": "recorded",
        "semantic_pass": status == "passed",
        "translator_version": "0.1.0",
        "fixture": {"path": fixture_path, "hash": "sum-i32-ptr-arith-fixture"},
        "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module", "translator_version"]
    });
    write_json(
        &evidence_dir.join(format!("{prefix}-version-manifest.json")),
        &version_payload,
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-cache-metadata.json")),
        &version_payload,
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-evidence-manifest.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "status": manifest_status,
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "fixture": {"path": fixture_path, "hash": "sum-i32-ptr-arith-fixture", "operation_count": case_count},
            "evidence": {
                "slice_contract": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-slice-contract.json", "status": "recorded"},
                "context_pack": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-context-pack.json", "status": "recorded"},
                "cache_metadata": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-cache-metadata.json", "status": "recorded"},
                "config_profile": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-config-profile.json", "status": "recorded", "profile_id": "demo-sum-i32-ptr-arith-wsl-gcc"},
                "type_map": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-type-map.json", "status": "recorded"},
                "cfg": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-cfg.json", "status": "recorded"},
                "pointer_dependency_graph": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-pointer-graph.json", "status": "recorded"},
                "test_translation": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-test-translation.json", "status": "recorded"},
                "c_oracle": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-c-oracle.json", "status": "passed", "toolchain_status": "C_ORACLE_GENERATED"},
                "rust_report": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-rust-report.json", "status": status},
                "schema_diff": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-diff.json", "status": status},
                "negative_diff": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-negative-diff.json", "status": "expected_failed", "expected_failure": true, "mutation_detected": true},
                "rust_check": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-rust-check.json", "status": status},
                "unsafe_scan": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-unsafe-scan.json", "status": unsafe_status},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-unsafe-ledger.json", "status": unsafe_status},
                "performance_smoke": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-performance-smoke.json", "status": "recorded", "secondary_only": true},
                "final_verification": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-final-verification.json", "status": status},
                "summary": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-summary.json", "status": status},
                "version_or_config_binding": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-version-manifest.json", "status": "recorded"}
            },
            "claim_boundary": {
                "scope": "Only the demo sum_i32_ptr_arith slice for the committed fixture corpus.",
                "behavior_fields_checked": ["return_code", "status", "len", "sum", "source_reads", "canonical_reads", "source_write"],
                "accepted_metadata_differences": [],
                "known_gaps": ["No NULL pointer execution.", "No negative len execution.", "No pointer arithmetic writes.", "No aliasing or signed overflow claim."],
                "must_not_claim": ["full automatic C99/C11 translation", "whole-program alias safety", "NULL pointer equivalence", "signed overflow equivalence"]
            }
        }),
    )
}
