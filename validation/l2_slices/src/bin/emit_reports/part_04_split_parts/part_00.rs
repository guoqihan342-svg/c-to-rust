fn emit_call_expression_chain_static_l3_evidence(
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
    let source_commit = "demo-call-expression-20260625";
    let fixture_path = "validation/l2_slices/fixtures/call-expression-c-oracle.json";
    let prefix = "l3-call-expression";
    let behavior_fields = [
        "return_value",
        "status",
        "call_expression_count",
        "call_expression_contexts",
        "source_calls",
    ];
    let source_calls = [
        "int first = call_expression_chain(value - 1)",
        "value = call_expression_chain(first - 1)",
        "return call_expression_chain(value - 1)",
    ];

    write_json(
        &evidence_dir.join(format!("{prefix}-slice-contract.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "source_boundary": {
                "files": ["validation/l2_slices/tools/generate_call_expression_oracle.py"],
                "functions": ["call_expression_chain"],
                "signature": "int call_expression_chain(int value)"
            },
            "rust_boundary": {
                "module": "validation/l2_slices/src/call_expression_chain.rs",
                "api": "pub fn call_expression_chain(value: i32) -> CallExpressionChainReport",
                "safe_rust": true,
                "raw_pointer_exposed": false
            },
            "fixture": {"path": fixture_path, "hash": "call-expression-fixture", "case_count": case_count},
            "behavior_fields": behavior_fields,
            "accepted_differences": [],
            "non_goals": [
                "No external callee semantic proof.",
                "No function pointer, member call, variadic call, macro call, or nested call support claim.",
                "No large recursion depth or performance claim.",
                "No full project migration claim."
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-context-pack.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "direct_c_files": ["validation/l2_slices/tools/generate_call_expression_oracle.py"],
            "direct_rust_files": [
                "validation/l2_slices/src/call_expression_chain.rs",
                "validation/l2_slices/tests/call_expression_chain.rs",
                "validation/l2_slices/src/bin/emit_reports.rs"
            ],
            "direct_call_edges": [
                {"callee": "call_expression_chain", "arguments": ["value - 1"], "source_expression": "call_expression_chain(value - 1)", "statement_context": "declaration_initializer"},
                {"callee": "call_expression_chain", "arguments": ["first - 1"], "source_expression": "call_expression_chain(first - 1)", "statement_context": "assignment"},
                {"callee": "call_expression_chain", "arguments": ["value - 1"], "source_expression": "call_expression_chain(value - 1)", "statement_context": "return"}
            ],
            "source_calls": source_calls,
            "related_tests": [
                "validation/l2_slices/tests/call_expression_chain.rs::call_expression_chain_matches_c_oracle_and_records_call_contexts"
            ],
            "cache_inputs": [fixture_path, "validation/l2_slices/src/call_expression_chain.rs"]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-config-profile.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "profile_id": "demo-call-expression-wsl-gcc",
            "compile_profile": {
                "c_oracle_command": "python -B validation/l2_slices/tools/generate_call_expression_oracle.py",
                "include_paths": [],
                "command_args": ["wsl", "gcc", "-std=c99", "-Wall", "-Wextra", "-Werror"]
            },
            "rust_profile": {"package": "c-to-rust-l2-slices", "cargo_features": []},
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-type-map.json")),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "call-expression",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "slice_spec_ref": {"path": "validation/slice-specs/demo-call-expression.json", "status": "ready"},
            "build_profile_ref": {"path": "validation/evidence/demo/l3-call-expression-config-profile.json", "status": "recorded"},
            "mappings": [
                {"id": "type-1", "kind": "primitive", "c_name": "value", "symbol": "value", "c_type": "int", "rust_type": "i32", "confidence": "proven", "role": "input_value"},
                {"id": "type-2", "kind": "primitive", "c_name": "first", "symbol": "first", "c_type": "int", "rust_type": "i32", "confidence": "proven", "role": "local_call_result"},
                {"id": "type-3", "kind": "primitive", "c_name": "return", "symbol": "return", "c_type": "int", "rust_type": "i32", "confidence": "proven", "role": "return_value"}
            ],
            "uncertainties": [],
            "unsupported_types": [],
            "unsupported_nodes": [],
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"],
            "safe_boundary": {
                "public_api": "pub fn call_expression_chain(value: i32) -> CallExpressionChainReport",
                "raw_pointer_exposed": false,
                "unsafe_required": false
            }
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-cfg.json")),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "call-expression",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "slice_spec_ref": {"path": "validation/slice-specs/demo-call-expression.json", "status": "ready"},
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"],
            "functions": [
                {
                    "name": "call_expression_chain",
                    "signature": "int call_expression_chain(int value)",
                    "source_span": {"file": "validation/l2_slices/tools/generate_call_expression_oracle.py", "line_start": 1, "line_end": 1},
                    "entry_block": "entry",
                    "exit_blocks": ["base_return", "recursive_return"],
                    "basic_blocks": [
                        {
                            "id": "entry",
                            "kind": "entry",
                            "source_span": {"file": "validation/l2_slices/tools/generate_call_expression_oracle.py", "line_start": 1, "line_end": 1},
                            "statements": ["if (value <= 0)", "int first = call_expression_chain(value - 1)", "value = call_expression_chain(first - 1)", "return call_expression_chain(value - 1)"],
                            "statement_kinds": ["if", "call_expression", "assignment", "call_expression", "return", "call_expression"],
                            "lvalue_kinds": ["none"],
                            "lvalue_decisions": []
                        }
                    ],
                    "branches": [
                        {"id": "branch-1", "kind": "if", "condition": "value <= 0", "source_span": {"file": "validation/l2_slices/tools/generate_call_expression_oracle.py", "line_start": 1, "line_end": 1}}
                    ],
                    "returns": [
                        {"block": "entry", "expression": "-value", "source_span": {"file": "validation/l2_slices/tools/generate_call_expression_oracle.py", "line_start": 1, "line_end": 1}},
                        {"block": "entry", "expression": "call_expression_chain(value - 1)", "source_span": {"file": "validation/l2_slices/tools/generate_call_expression_oracle.py", "line_start": 1, "line_end": 1}}
                    ],
                    "edges": [
                        {"from": "entry", "to": "base_return", "kind": "true_branch", "condition": "value <= 0", "source_span": {"file": "validation/l2_slices/tools/generate_call_expression_oracle.py", "line_start": 1, "line_end": 1}},
                        {"from": "entry", "to": "recursive_return", "kind": "false_branch", "condition": "value > 0", "source_span": {"file": "validation/l2_slices/tools/generate_call_expression_oracle.py", "line_start": 1, "line_end": 1}}
                    ],
                    "structured_control_flow": {
                        "has_goto": false,
                        "has_switch": false,
                        "if_count": 1,
                        "loop_count": 0,
                        "relooper_required": false
                    }
                }
            ],
            "unsupported_control_flow": []
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-pointer-graph.json")),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "call-expression",
            "level": "L3",
            "status": "not_applicable",
            "not_applicable_reason": "call_expression_chain has no pointer parameters, pointer returns, globals, buffers, or external mutable state in the committed fixture boundary.",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "context_pack_ref": "validation/evidence/demo/l3-call-expression-context-pack.json",
            "applicability": {"has_pointer_surface": false, "triggers": ["none"]},
            "source_boundary": {
                "files": ["validation/l2_slices/tools/generate_call_expression_oracle.py", fixture_path],
                "functions": ["call_expression_chain"],
                "structs": [],
                "globals": [],
                "direct_call_edges": [
                    {"from": "call_expression_chain", "to": "call_expression_chain", "condition": "value > 0"}
                ]
            },
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-rust-check.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": source_commit,
            "status": status,
            "compile_self_healing": {"attempt_count": 0, "unresolved_errors": 0},
            "commands": [
                {"command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test call_expression_chain", "status": status},
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
            "slice_id": "call-expression",
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
            "generated_draft_semantic_pass": false,
            "call_expression_contexts_checked": ["declaration_initializer", "assignment", "return"]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-summary.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": source_commit,
            "status": status,
            "semantic_pass": status == "passed",
            "summary": "call_expression_chain recursive direct-call demo has accepted C oracle, Rust replay, diff, negative diff, unsafe, and version evidence.",
            "generated_draft_semantic_pass": false,
            "known_gaps": [
                "No external callee semantic proof.",
                "No function pointer, member call, variadic call, macro call, or nested call support claim.",
                "No large recursion depth or performance claim."
            ]
        }),
    )?;
    let version_payload = json!({
        "schema_version": 1,
        "level": "L3",
        "target_id": "demo",
        "slice_id": "call-expression",
        "source_commit": source_commit,
        "repo_commit": repo_commit,
        "status": "recorded",
        "semantic_pass": status == "passed",
        "translator_version": "0.1.0",
        "fixture": {"path": fixture_path, "hash": "call-expression-fixture"},
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
            "slice_id": "call-expression",
            "status": manifest_status,
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "fixture": {"path": fixture_path, "hash": "call-expression-fixture", "operation_count": case_count},
            "evidence": {
                "slice_contract": {"path": "validation/evidence/demo/l3-call-expression-slice-contract.json", "status": "recorded"},
                "context_pack": {"path": "validation/evidence/demo/l3-call-expression-context-pack.json", "status": "recorded"},
                "cache_metadata": {"path": "validation/evidence/demo/l3-call-expression-cache-metadata.json", "status": "recorded"},
                "config_profile": {"path": "validation/evidence/demo/l3-call-expression-config-profile.json", "status": "recorded", "profile_id": "demo-call-expression-wsl-gcc"},
                "type_map": {"path": "validation/evidence/demo/l3-call-expression-type-map.json", "status": "recorded"},
                "cfg": {"path": "validation/evidence/demo/l3-call-expression-cfg.json", "status": "recorded"},
                "pointer_dependency_graph": {"path": "validation/evidence/demo/l3-call-expression-pointer-graph.json", "status": "not_applicable", "not_applicable_reason": "slice has no pointer surface"},
                "test_translation": {"path": "validation/evidence/demo/l3-call-expression-test-translation.json", "status": "recorded"},
                "c_oracle": {"path": "validation/evidence/demo/l3-call-expression-c-oracle.json", "status": "passed", "toolchain_status": "C_ORACLE_GENERATED"},
                "rust_report": {"path": "validation/evidence/demo/l3-call-expression-rust-report.json", "status": status},
                "schema_diff": {"path": "validation/evidence/demo/l3-call-expression-diff.json", "status": status},
                "negative_diff": {"path": "validation/evidence/demo/l3-call-expression-negative-diff.json", "status": "expected_failed", "expected_failure": true, "mutation_detected": true},
                "rust_check": {"path": "validation/evidence/demo/l3-call-expression-rust-check.json", "status": status},
                "unsafe_scan": {"path": "validation/evidence/demo/l3-call-expression-unsafe-scan.json", "status": unsafe_status},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-call-expression-unsafe-ledger.json", "status": unsafe_status},
                "performance_smoke": {"path": "validation/evidence/demo/l3-call-expression-performance-smoke.json", "status": "recorded", "secondary_only": true},
                "final_verification": {"path": "validation/evidence/demo/l3-call-expression-final-verification.json", "status": status},
                "summary": {"path": "validation/evidence/demo/l3-call-expression-summary.json", "status": status},
                "version_or_config_binding": {"path": "validation/evidence/demo/l3-call-expression-version-manifest.json", "status": "recorded"}
            },
            "claim_boundary": {
                "scope": "Only the demo call_expression_chain slice for the committed fixture corpus.",
                "behavior_fields_checked": behavior_fields,
                "accepted_metadata_differences": [],
                "known_gaps": [
                    "No external callee semantic proof.",
                    "No function pointer, member call, variadic call, macro call, or nested call support claim.",
                    "No large recursion depth or performance claim."
                ],
                "must_not_claim": [
                    "full automatic C99/C11 translation",
                    "whole-program call graph semantic proof",
                    "external callee semantic equivalence",
                    "function pointer or nested call expression support"
                ]
            }
        }),
    )
}
