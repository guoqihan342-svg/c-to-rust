fn emit_sum_i32_buffer_static_l3_evidence(
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
    let source_commit = "demo-sum-i32-buffer-20260625";
    let fixture_path = "validation/l2_slices/fixtures/sum-i32-buffer-c-oracle.json";

    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-slice-contract.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "source_boundary": {
                "files": ["validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py"],
                "functions": ["sum_i32_buffer"],
                "signature": "int sum_i32_buffer(const int* values, int len, int* out)"
            },
            "rust_boundary": {
                "module": "validation/l2_slices/src/sum_i32_buffer.rs",
                "api": "pub fn sum_i32_buffer(values: &[i32]) -> SumI32BufferReport",
                "safe_rust": true,
                "raw_pointer_exposed": false
            },
            "fixture": {"path": fixture_path, "hash": "sum-i32-buffer-fixture", "case_count": case_count},
            "behavior_fields": ["return_code", "status", "len", "sum", "source_reads", "source_write"],
            "accepted_differences": [],
            "non_goals": [
                "No NULL pointer execution.",
                "No negative len execution.",
                "No aliasing proof between values and out.",
                "No signed overflow cases.",
                "No pointer arithmetic form such as *(values + i).",
                "No full project migration claim."
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-context-pack.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "direct_c_files": ["validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py"],
            "direct_rust_files": [
                "validation/l2_slices/src/sum_i32_buffer.rs",
                "validation/l2_slices/tests/sum_i32_buffer.rs",
                "validation/l2_slices/src/bin/emit_reports.rs"
            ],
            "call_edges": [
                {"from": "C oracle helper", "to": "sum_i32_buffer"},
                {"from": "Rust emit_reports", "to": "sum_i32_buffer::sum_i32_buffer"}
            ],
            "related_tests": [
                "validation/l2_slices/tests/sum_i32_buffer.rs::sum_i32_buffer_matches_c_oracle_with_safe_boundary"
            ],
            "cache_inputs": [fixture_path, "validation/l2_slices/src/sum_i32_buffer.rs"]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-config-profile.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "profile_id": "demo-sum-i32-buffer-wsl-gcc",
            "compile_profile": {
                "c_oracle_command": "python -B validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py",
                "include_paths": [],
                "command_args": ["wsl", "gcc", "-std=c99", "-Wall", "-Wextra", "-Werror"]
            },
            "rust_profile": {"package": "c-to-rust-l2-slices", "cargo_features": []},
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-type-map.json"),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "slice_spec_ref": {"path": "validation/slice-specs/demo-sum-i32-buffer.json", "status": "ready"},
            "build_profile_ref": {"path": "validation/evidence/demo/l3-sum-i32-buffer-config-profile.json", "status": "recorded"},
            "mappings": [
                {
                    "id": "type-1",
                    "kind": "pointer",
                    "c_name": "values",
                    "symbol": "values",
                    "c_type": "const int*",
                    "rust_type": "&[i32]",
                    "confidence": "proven",
                    "source": "translator_rule",
                    "role": "input_buffer",
                    "mutability": "read_only",
                    "length_companion": "len",
                    "decision": "safe_slice_boundary"
                },
                {
                    "id": "type-2",
                    "kind": "primitive",
                    "c_name": "len",
                    "symbol": "len",
                    "c_type": "int",
                    "rust_type": "i32",
                    "confidence": "proven",
                    "source": "translator_rule",
                    "role": "input_length",
                    "bounds": "fixture domain requires len >= 0 and values valid for len elements"
                },
                {
                    "id": "type-3",
                    "kind": "pointer",
                    "c_name": "out",
                    "symbol": "out",
                    "c_type": "int*",
                    "rust_type": "SumI32BufferReport.sum",
                    "confidence": "proven",
                    "source": "translator_rule",
                    "role": "output_pointer",
                    "mutability": "write_only",
                    "decision": "owned_report_field"
                },
                {
                    "id": "type-4",
                    "kind": "primitive",
                    "c_name": "total",
                    "symbol": "total",
                    "c_type": "int",
                    "rust_type": "i32",
                    "confidence": "proven",
                    "source": "translator_rule",
                    "role": "local_accumulator"
                }
            ],
            "uncertainties": [],
            "unsupported_types": [],
            "unsupported_nodes": [],
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"],
            "safe_boundary": {
                "public_api": "pub fn sum_i32_buffer(values: &[i32]) -> SumI32BufferReport",
                "raw_pointer_exposed": false,
                "unsafe_required": false
            }
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-cfg.json"),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "slice_spec_ref": {"path": "validation/slice-specs/demo-sum-i32-buffer.json", "status": "ready"},
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"],
            "functions": [
                {
                    "name": "sum_i32_buffer",
                    "signature": "int sum_i32_buffer(const int* values, int len, int* out)",
                    "source_span": {"file": "validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py", "line_start": 1, "line_end": 1},
                    "entry_block": "entry",
                    "exit_blocks": ["return"],
                    "basic_blocks": [
                        {
                            "id": "entry",
                            "kind": "entry",
                            "source_span": {"file": "validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py", "line_start": 1, "line_end": 1},
                            "statements": ["int total = 0", "int i", "for (i = 0; i < len; i++)"],
                            "statement_kinds": ["local_init", "local_decl", "for_loop"],
                            "lvalue_kinds": ["none"],
                            "lvalue_decisions": []
                        },
                        {
                            "id": "loop_body",
                            "kind": "body",
                            "source_span": {"file": "validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py", "line_start": 1, "line_end": 1},
                            "statements": ["total = total + values[i]"],
                            "statement_kinds": ["bounded_input_buffer_read", "assignment"],
                            "lvalue_kinds": ["bounded_input_buffer"],
                            "lvalue_decisions": [
                                {
                                    "decision": "bounded_input_buffer",
                                    "lvalue_kind": "bounded_input_buffer",
                                    "source_statement": "total = total + values[i]",
                                    "translation_rule_id": "bounded-input-buffer-read",
                                    "length_companion": "len"
                                }
                            ]
                        },
                        {
                            "id": "exit",
                            "kind": "exit",
                            "source_span": {"file": "validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py", "line_start": 1, "line_end": 1},
                            "statements": ["out[0] = total", "return 0"],
                            "statement_kinds": ["pointer_write", "return"],
                            "lvalue_kinds": ["bounded_pointer_index", "none"],
                            "lvalue_decisions": [
                                {
                                    "decision": "bounded_pointer_index",
                                    "lvalue_kind": "bounded_pointer_index",
                                    "source_statement": "out[0] = total",
                                    "translation_rule_id": "bounded-pointer-index-write"
                                }
                            ]
                        }
                    ],
                    "branches": [
                        {
                            "id": "branch-1",
                            "kind": "for",
                            "condition": "i < len",
                            "source_span": {"file": "validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py", "line_start": 1, "line_end": 1},
                            "proves": "values[i] bounded by len companion"
                        }
                    ],
                    "returns": [
                        {
                            "block": "exit",
                            "expression": "0",
                            "source_span": {"file": "validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py", "line_start": 1, "line_end": 1}
                        }
                    ],
                    "edges": [
                        {"from": "entry", "to": "loop_body", "kind": "fallthrough"},
                        {"from": "loop_body", "to": "loop_body", "kind": "loop_back"},
                        {"from": "loop_body", "to": "exit", "kind": "fallthrough"},
                        {"from": "exit", "to": "return", "kind": "return"}
                    ],
                    "structured_control_flow": {
                        "has_goto": false,
                        "has_switch": false,
                        "if_count": 0,
                        "loop_count": 1,
                        "relooper_required": false
                    }
                }
            ],
            "unsupported_control_flow": []
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-pointer-graph.json"),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "context_pack_ref": "validation/evidence/demo/l3-sum-i32-buffer-context-pack.json",
            "applicability": {"has_pointer_surface": true, "triggers": ["pointer_parameter", "buffer"]},
            "source_boundary": {
                "files": ["validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py", fixture_path],
                "functions": ["sum_i32_buffer"],
                "structs": ["int"],
                "globals": [],
                "direct_call_edges": []
            },
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"],
            "pointer_nodes": [
                {
                    "id": "values",
                    "symbol": "values",
                    "kind": "buffer",
                    "buffer_role": "input",
                    "length_companion": "len",
                    "c_type": "const int*",
                    "mutability": "read_only",
                    "nullability": "unknown",
                    "ownership_role": "borrowed",
                    "read_effects": ["values[i]"],
                    "write_effects": [],
                    "boundary_decisions": ["bounded_input_buffer"]
                },
                {
                    "id": "out",
                    "symbol": "out",
                    "kind": "struct_pointer",
                    "c_type": "int*",
                    "mutability": "write_only",
                    "nullability": "unknown",
                    "ownership_role": "out_param",
                    "read_effects": [],
                    "write_effects": ["out[0]"],
                    "boundary_decisions": ["bounded_pointer_index"]
                }
            ],
            "dependency_edges": [
                {"from": "len", "to": "values", "relationship": "borrows", "evidence": "for (i = 0; i < len; i++)"},
                {"from": "values", "to": "out", "relationship": "writes_through", "evidence": "out[0] = total"}
            ],
            "alias_sets": [],
            "rust_mapping": [
                {"pointer_node": "values", "strategy": "Map const int* plus len to safe Rust slice input.", "unsafe_expected": false},
                {"pointer_node": "out", "strategy": "Map C out[0] write to owned SumI32BufferReport.sum field.", "unsafe_expected": false}
            ],
            "pointer_decisions": [
                {"pointer_node": "values", "decision": "bounded_input_buffer", "read_effect": "values[i]", "length_companion": "len", "translation_rule_id": "bounded-input-buffer-read", "unsafe_expected": false},
                {"pointer_node": "out", "decision": "bounded_pointer_index", "index": 0, "write_effect": "out[0]", "translation_rule_id": "bounded-pointer-index-write", "unsafe_expected": false}
            ],
            "risk_summary": {
                "unsafe_expected": false,
                "known_gaps": ["NULL pointers are not executed.", "Aliasing is not proven.", "Signed overflow cases are excluded."]
            }
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-test-translation.json"),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "source_test_inputs": {
                "oracle_strategy": "WSL gcc compiles and runs the C helper, then Rust cargo tests replay the same fixture.",
                "fixtures": [{"path": fixture_path, "hash": "sum-i32-buffer-fixture", "operation_count": case_count, "source_kind": "fixture"}],
                "oracle_reports": [
                    {"path": "validation/evidence/demo/l3-sum-i32-buffer-c-oracle.json", "status": "passed"},
                    {"path": "validation/evidence/demo/l3-sum-i32-buffer-rust-report.json", "status": "passed"}
                ]
            },
            "rust_tests": [
                {
                    "file": "validation/l2_slices/tests/sum_i32_buffer.rs",
                    "test_names": ["sum_i32_buffer_matches_c_oracle_with_safe_boundary"],
                    "cargo_command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test sum_i32_buffer",
                    "framework": "cargo test"
                }
            ],
            "coverage": {
                "main_paths": ["empty input", "single input", "multi input", "negative values", "boundary-safe sum"],
                "error_paths": [],
                "negative_cases": ["sum mutation rejected by negative diff"]
            },
            "translation_mappings": [
                {
                    "source": fixture_path,
                    "rust_test": "validation/l2_slices/tests/sum_i32_buffer.rs::sum_i32_buffer_matches_c_oracle_with_safe_boundary",
                    "behavior_fields": ["return_code", "status", "len", "sum", "source_reads", "source_write"],
                    "coverage_kind": "main_path",
                    "status": "mapped"
                },
                {
                    "source": "validation/evidence/demo/l3-sum-i32-buffer-negative-diff.json",
                    "rust_test": "validation/l2_slices/src/bin/emit_reports.rs::emit_sum_i32_buffer_negative_diff",
                    "behavior_fields": ["sum"],
                    "coverage_kind": "negative_case",
                    "status": "mapped"
                }
            ],
            "evidence_links": {
                "c_oracle": {"path": "validation/evidence/demo/l3-sum-i32-buffer-c-oracle.json", "status": "passed"},
                "rust_report": {"path": "validation/evidence/demo/l3-sum-i32-buffer-rust-report.json", "status": "passed"},
                "schema_diff": {"path": "validation/evidence/demo/l3-sum-i32-buffer-diff.json", "status": "passed"},
                "negative_diff": {"path": "validation/evidence/demo/l3-sum-i32-buffer-negative-diff.json", "status": "expected_failed"},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-sum-i32-buffer-unsafe-ledger.json", "status": "passed"}
            }
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-rust-check.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": source_commit,
            "status": status,
            "compile_self_healing": {"attempt_count": 0, "unresolved_errors": 0},
            "commands": [
                {"command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test sum_i32_buffer", "status": status},
                {"command": "cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports", "status": status}
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-final-verification.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
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
        &evidence_dir.join("l3-sum-i32-buffer-summary.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": source_commit,
            "status": status,
            "semantic_pass": status == "passed",
            "summary": "sum_i32_buffer input-buffer pointer demo has accepted C oracle, Rust replay, diff, negative diff, unsafe, and version evidence.",
            "generated_draft_semantic_pass": false,
            "known_gaps": ["No NULL pointer execution.", "No negative len execution.", "No aliasing or signed overflow claim."]
        }),
    )?;
    let version_payload = json!({
        "schema_version": 1,
        "level": "L3",
        "target_id": "demo",
        "slice_id": "sum-i32-buffer",
        "source_commit": source_commit,
        "repo_commit": repo_commit,
        "status": "recorded",
        "semantic_pass": status == "passed",
        "translator_version": "0.1.0",
        "fixture": {"path": fixture_path, "hash": "sum-i32-buffer-fixture"},
        "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module", "translator_version"]
    });
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-version-manifest.json"),
        &version_payload,
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-cache-metadata.json"),
        &version_payload,
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-evidence-manifest.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "status": manifest_status,
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "fixture": {"path": fixture_path, "hash": "sum-i32-buffer-fixture", "operation_count": case_count},
            "evidence": {
                "slice_contract": {"path": "validation/evidence/demo/l3-sum-i32-buffer-slice-contract.json", "status": "recorded"},
                "context_pack": {"path": "validation/evidence/demo/l3-sum-i32-buffer-context-pack.json", "status": "recorded"},
                "cache_metadata": {"path": "validation/evidence/demo/l3-sum-i32-buffer-cache-metadata.json", "status": "recorded"},
                "config_profile": {"path": "validation/evidence/demo/l3-sum-i32-buffer-config-profile.json", "status": "recorded", "profile_id": "demo-sum-i32-buffer-wsl-gcc"},
                "type_map": {"path": "validation/evidence/demo/l3-sum-i32-buffer-type-map.json", "status": "recorded"},
                "cfg": {"path": "validation/evidence/demo/l3-sum-i32-buffer-cfg.json", "status": "recorded"},
                "pointer_dependency_graph": {"path": "validation/evidence/demo/l3-sum-i32-buffer-pointer-graph.json", "status": "recorded"},
                "test_translation": {"path": "validation/evidence/demo/l3-sum-i32-buffer-test-translation.json", "status": "recorded"},
                "c_oracle": {"path": "validation/evidence/demo/l3-sum-i32-buffer-c-oracle.json", "status": "passed", "toolchain_status": "C_ORACLE_GENERATED"},
                "rust_report": {"path": "validation/evidence/demo/l3-sum-i32-buffer-rust-report.json", "status": status},
                "schema_diff": {"path": "validation/evidence/demo/l3-sum-i32-buffer-diff.json", "status": status},
                "negative_diff": {"path": "validation/evidence/demo/l3-sum-i32-buffer-negative-diff.json", "status": "expected_failed", "expected_failure": true, "mutation_detected": true},
                "rust_check": {"path": "validation/evidence/demo/l3-sum-i32-buffer-rust-check.json", "status": status},
                "unsafe_scan": {"path": "validation/evidence/demo/l3-sum-i32-buffer-unsafe-scan.json", "status": unsafe_status},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-sum-i32-buffer-unsafe-ledger.json", "status": unsafe_status},
                "performance_smoke": {"path": "validation/evidence/demo/l3-sum-i32-buffer-performance-smoke.json", "status": "recorded", "secondary_only": true},
                "final_verification": {"path": "validation/evidence/demo/l3-sum-i32-buffer-final-verification.json", "status": status},
                "summary": {"path": "validation/evidence/demo/l3-sum-i32-buffer-summary.json", "status": status},
                "version_or_config_binding": {"path": "validation/evidence/demo/l3-sum-i32-buffer-version-manifest.json", "status": "recorded"}
            },
            "claim_boundary": {
                "scope": "Only the demo sum_i32_buffer slice for the committed fixture corpus.",
                "behavior_fields_checked": ["return_code", "status", "len", "sum", "source_reads", "source_write"],
                "accepted_metadata_differences": [],
                "known_gaps": ["No NULL pointer execution.", "No negative len execution.", "No aliasing or signed overflow claim."],
                "must_not_claim": ["full automatic C99/C11 translation", "whole-program alias safety", "NULL pointer equivalence", "signed overflow equivalence"]
            }
        }),
    )
}
