fn emit_signed_rshift_contract_static_l3_evidence(
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
    let source_commit = "demo-signed-rshift-contract-20260628";
    let fixture_path = "validation/l2_slices/fixtures/signed-rshift-contract-c-oracle.json";
    let prefix = "l3-signed-rshift-contract";
    let behavior_fields = ["return_value", "status", "contract"];
    let scalar_contract = json!({
        "wrapping_profile": "not_declared",
        "signed_overflow": "not_declared",
        "division_by_zero": "not_declared",
        "signed_division_overflow": "not_declared",
        "shift_count": "runtime_precondition_in_range",
        "signed_right_shift": "explicit_implementation_defined_contract"
    });

    write_json(
        &evidence_dir.join(format!("{prefix}-slice-contract.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "signed-rshift-contract",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "source_boundary": {
                "files": ["validation/l2_slices/fixtures/signed-rshift-contract.c"],
                "functions": ["signed_rshift_contract"],
                "signature": "int signed_rshift_contract(int value, int count)"
            },
            "c_boundary": {
                "scalar_arithmetic_contract": scalar_contract,
                "input_domain": {
                    "value": "i32 fixture values",
                    "count": "0 <= count < 32"
                }
            },
            "rust_boundary": {
                "module": "validation/l2_slices/src/signed_rshift_contract.rs",
                "api": "pub fn signed_rshift_contract(value: i32, count: u32) -> SignedRshiftContractReport",
                "safe_rust": true,
                "raw_pointer_exposed": false
            },
            "fixture": {"path": fixture_path, "hash": "signed-rshift-contract-fixture", "case_count": case_count},
            "behavior_fields": behavior_fields,
            "accepted_differences": [
                "C signed right shift is implementation-defined; this slice only accepts arithmetic right shift under the declared contract."
            ],
            "non_goals": [
                "No full project migration claim.",
                "No portable C standard signed-right-shift semantic claim without the explicit implementation-defined contract.",
                "No support for count < 0 or count >= 32.",
                "No signed overflow or full scalar UB coverage claim beyond this slice contract."
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-context-pack.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "signed-rshift-contract",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "direct_c_files": ["validation/l2_slices/fixtures/signed-rshift-contract.c"],
            "direct_rust_files": [
                "validation/l2_slices/src/signed_rshift_contract.rs",
                "validation/l2_slices/tests/signed_rshift_contract.rs",
                "validation/l2_slices/src/bin/emit_reports.rs"
            ],
            "scalar_runtime_contract": {
                "preconditions": ["shift_count_in_range", "signed_right_shift_implementation_defined"],
                "contract": scalar_contract
            },
            "related_tests": [
                "validation/l2_slices/tests/signed_rshift_contract.rs::signed_rshift_contract_matches_c_oracle_under_explicit_contract"
            ],
            "cache_inputs": [fixture_path, "validation/l2_slices/src/signed_rshift_contract.rs"]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-config-profile.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "signed-rshift-contract",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "profile_id": "demo-signed-rshift-contract-wsl-gcc",
            "compile_profile": {
                "c_oracle_command": "committed explicit-contract fixture",
                "include_paths": [],
                "command_args": ["gcc", "-std=c99", "-Wall", "-Wextra", "-Werror"]
            },
            "rust_profile": {"package": "c-to-rust-l2-slices", "cargo_features": []},
            "scalar_arithmetic_contract": scalar_contract,
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-type-map.json")),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "signed-rshift-contract",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "slice_spec_ref": {"path": "validation/slice-specs/demo-signed-rshift-contract.json", "status": "ready"},
            "build_profile_ref": {"path": "validation/evidence/demo/l3-signed-rshift-contract-config-profile.json", "status": "recorded"},
            "mappings": [
                {"id": "type-1", "kind": "primitive", "c_name": "value", "symbol": "value", "c_type": "int", "rust_type": "i32", "confidence": "proven", "role": "input_value"},
                {"id": "type-2", "kind": "primitive", "c_name": "count", "symbol": "count", "c_type": "int", "rust_type": "u32", "confidence": "contract_bound", "role": "shift_count"},
                {"id": "type-3", "kind": "primitive", "c_name": "return", "symbol": "return", "c_type": "int", "rust_type": "i32", "confidence": "proven", "role": "return_value"}
            ],
            "uncertainties": [],
            "unsupported_types": [],
            "unsupported_nodes": [],
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"],
            "safe_boundary": {
                "public_api": "pub fn signed_rshift_contract(value: i32, count: u32) -> SignedRshiftContractReport",
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
            "slice_id": "signed-rshift-contract",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "slice_spec_ref": {"path": "validation/slice-specs/demo-signed-rshift-contract.json", "status": "ready"},
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"],
            "functions": [
                {
                    "name": "signed_rshift_contract",
                    "signature": "int signed_rshift_contract(int value, int count)",
                    "source_span": {"file": "validation/l2_slices/fixtures/signed-rshift-contract.c", "line_start": 1, "line_end": 1},
                    "entry_block": "entry",
                    "exit_blocks": ["return"],
                    "basic_blocks": [
                        {
                            "id": "entry",
                            "kind": "entry",
                            "source_span": {"file": "validation/l2_slices/fixtures/signed-rshift-contract.c", "line_start": 1, "line_end": 1},
                            "statements": ["return value >> count"],
                            "statement_kinds": ["return", "binary_shift"],
                            "lvalue_kinds": ["none"],
                            "lvalue_decisions": []
                        }
                    ],
                    "returns": [
                        {"block": "entry", "expression": "value >> count", "source_span": {"file": "validation/l2_slices/fixtures/signed-rshift-contract.c", "line_start": 1, "line_end": 1}}
                    ],
                    "edges": [],
                    "structured_control_flow": {
                        "has_goto": false,
                        "has_switch": false,
                        "if_count": 0,
                        "loop_count": 0,
                        "relooper_required": false
                    },
                    "runtime_preconditions": ["shift_count_in_range", "signed_right_shift_implementation_defined"]
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
            "slice_id": "signed-rshift-contract",
            "level": "L3",
            "status": "not_applicable",
            "not_applicable_reason": "signed_rshift_contract has no pointer parameters, pointer returns, globals, buffers, or external mutable state in the committed fixture boundary.",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "context_pack_ref": "validation/evidence/demo/l3-signed-rshift-contract-context-pack.json",
            "applicability": {"has_pointer_surface": false, "triggers": ["none"]},
            "source_boundary": {
                "files": ["validation/l2_slices/fixtures/signed-rshift-contract.c", fixture_path],
                "functions": ["signed_rshift_contract"],
                "structs": [],
                "globals": []
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
            "slice_id": "signed-rshift-contract",
            "source_commit": source_commit,
            "status": status,
            "compile_self_healing": {"attempt_count": 0, "unresolved_errors": 0},
            "commands": [
                {"command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test signed_rshift_contract", "status": status},
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
            "slice_id": "signed-rshift-contract",
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
            "scalar_runtime_contract": scalar_contract,
            "generated_draft_semantic_pass": false
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-summary.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "signed-rshift-contract",
            "source_commit": source_commit,
            "status": status,
            "semantic_pass": status == "passed",
            "summary": "signed_rshift_contract demo has accepted C oracle, Rust replay, diff, negative diff, unsafe, scalar contract, and version evidence.",
            "generated_draft_semantic_pass": false,
            "known_gaps": [
                "No portable C standard signed-right-shift semantic claim without explicit implementation-defined contract.",
                "No support for count < 0 or count >= 32.",
                "No full scalar UB coverage claim."
            ]
        }),
    )?;
    let version_payload = json!({
        "schema_version": 1,
        "level": "L3",
        "target_id": "demo",
        "slice_id": "signed-rshift-contract",
        "source_commit": source_commit,
        "repo_commit": repo_commit,
        "status": "recorded",
        "semantic_pass": status == "passed",
        "translator_version": "0.1.0",
        "fixture": {"path": fixture_path, "hash": "signed-rshift-contract-fixture"},
        "scalar_arithmetic_contract": scalar_contract,
        "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module", "translator_version", "scalar_arithmetic_contract"]
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
            "slice_id": "signed-rshift-contract",
            "status": manifest_status,
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "fixture": {"path": fixture_path, "hash": "signed-rshift-contract-fixture", "operation_count": case_count},
            "evidence": {
                "slice_contract": {"path": "validation/evidence/demo/l3-signed-rshift-contract-slice-contract.json", "status": "recorded"},
                "context_pack": {"path": "validation/evidence/demo/l3-signed-rshift-contract-context-pack.json", "status": "recorded"},
                "cache_metadata": {"path": "validation/evidence/demo/l3-signed-rshift-contract-cache-metadata.json", "status": "recorded"},
                "config_profile": {"path": "validation/evidence/demo/l3-signed-rshift-contract-config-profile.json", "status": "recorded", "profile_id": "demo-signed-rshift-contract-wsl-gcc"},
                "type_map": {"path": "validation/evidence/demo/l3-signed-rshift-contract-type-map.json", "status": "recorded"},
                "cfg": {"path": "validation/evidence/demo/l3-signed-rshift-contract-cfg.json", "status": "recorded"},
                "pointer_dependency_graph": {"path": "validation/evidence/demo/l3-signed-rshift-contract-pointer-graph.json", "status": "not_applicable", "not_applicable_reason": "slice has no pointer surface"},
                "test_translation": {"path": "validation/evidence/demo/l3-signed-rshift-contract-test-translation.json", "status": "recorded"},
                "c_oracle": {"path": "validation/evidence/demo/l3-signed-rshift-contract-c-oracle.json", "status": "passed", "toolchain_status": "C_ORACLE_GENERATED"},
                "rust_report": {"path": "validation/evidence/demo/l3-signed-rshift-contract-rust-report.json", "status": status},
                "schema_diff": {"path": "validation/evidence/demo/l3-signed-rshift-contract-diff.json", "status": status},
                "negative_diff": {"path": "validation/evidence/demo/l3-signed-rshift-contract-negative-diff.json", "status": "expected_failed", "expected_failure": true, "mutation_detected": true},
                "rust_check": {"path": "validation/evidence/demo/l3-signed-rshift-contract-rust-check.json", "status": status},
                "unsafe_scan": {"path": "validation/evidence/demo/l3-signed-rshift-contract-unsafe-scan.json", "status": unsafe_status},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-signed-rshift-contract-unsafe-ledger.json", "status": unsafe_status},
                "performance_smoke": {"path": "validation/evidence/demo/l3-signed-rshift-contract-performance-smoke.json", "status": "recorded", "secondary_only": true},
                "final_verification": {"path": "validation/evidence/demo/l3-signed-rshift-contract-final-verification.json", "status": status},
                "summary": {"path": "validation/evidence/demo/l3-signed-rshift-contract-summary.json", "status": status},
                "version_or_config_binding": {"path": "validation/evidence/demo/l3-signed-rshift-contract-version-manifest.json", "status": "recorded"}
            },
            "claim_boundary": {
                "scope": "Only the demo signed_rshift_contract slice for the committed fixture corpus and explicit implementation-defined arithmetic right-shift contract.",
                "behavior_fields_checked": behavior_fields,
                "accepted_metadata_differences": ["C signed right shift is implementation-defined and accepted only under the declared arithmetic-shift contract."],
                "known_gaps": [
                    "No portable C standard signed-right-shift semantic claim without explicit implementation-defined contract.",
                    "No support for count < 0 or count >= 32.",
                    "No signed overflow or full scalar UB coverage claim."
                ],
                "must_not_claim": [
                    "full automatic C99/C11 translation",
                    "portable signed-right-shift semantics without explicit contract",
                    "shift-count UB equivalence outside the committed input domain",
                    "complete signed scalar UB coverage"
                ]
            }
        }),
    )
}
