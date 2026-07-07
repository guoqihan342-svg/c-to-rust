fn emit_sum_i32_buffer_static_l3_core_evidence(
    evidence_dir: &Path,
    case_count: usize,
    _status: &str,
    _unsafe_status: &str,
    repo_commit: &str,
    source_commit: &str,
    fixture_path: &str,
) -> Result<(), Box<dyn Error>> {
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
    Ok(())
}
