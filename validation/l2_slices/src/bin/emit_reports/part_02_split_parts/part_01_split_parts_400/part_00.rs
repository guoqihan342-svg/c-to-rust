fn emit_l2_test_translation(spec: L2TestTranslationSpec<'_>) -> Result<(), Box<dyn Error>> {
    let rust_test = format!(
        "validation/l2_slices/tests/oracle_fixtures.rs::{}",
        spec.rust_test_name
    );
    write_json(
        &spec
            .evidence_dir
            .join(format!("{}-test-translation.json", spec.slice_id)),
        &json!({
            "schema_version": 1,
            "target_id": spec.target_id,
            "slice_id": spec.slice_id,
            "level": "L2",
            "status": "recorded",
            "source_commit": spec.source_commit,
            "repo_commit": "workspace",
            "source_test_inputs": {
                "oracle_strategy": "Committed C oracle fixture is replayed by Rust cargo tests and emit_reports evidence generation.",
                "fixtures": [
                    {
                        "path": relative_path(spec.fixture_path),
                        "source_kind": "fixture"
                    }
                ],
                "oracle_reports": [
                    {
                        "path": format!("validation/evidence/l2-slices/{}-oracle.json", spec.slice_id),
                        "status": "passed"
                    }
                ]
            },
            "rust_tests": [
                {
                    "file": "validation/l2_slices/tests/oracle_fixtures.rs",
                    "test_names": [spec.rust_test_name],
                    "cargo_command": "cargo test --manifest-path validation/l2_slices/Cargo.toml",
                    "framework": "cargo test"
                }
            ],
            "coverage": {
                "main_paths": spec.main_paths,
                "error_paths": spec.error_paths,
                "negative_cases": spec.negative_cases
            },
            "translation_mappings": [
                {
                    "source": relative_path(spec.fixture_path),
                    "rust_test": rust_test,
                    "behavior_fields": spec.behavior_fields,
                    "coverage_kind": "main_path",
                    "status": "mapped"
                },
                {
                    "source": format!("validation/evidence/l2-slices/{}-negative-diff.json", spec.slice_id),
                    "rust_test": "validation/l2_slices/src/bin/emit_reports.rs::emit_negative_diffs",
                    "behavior_fields": spec.behavior_fields,
                    "coverage_kind": "negative_case",
                    "status": "mapped"
                }
            ],
            "evidence_links": {
                "c_oracle": {
                    "path": format!("validation/evidence/l2-slices/{}-oracle.json", spec.slice_id),
                    "status": "passed"
                },
                "rust_report": {
                    "path": format!("validation/evidence/l2-slices/{}-rust-report.json", spec.slice_id),
                    "status": "passed"
                },
                "schema_diff": {
                    "path": format!("validation/evidence/l2-slices/{}-diff.json", spec.slice_id),
                    "status": "passed"
                },
                "negative_diff": {
                    "path": format!("validation/evidence/l2-slices/{}-negative-diff.json", spec.slice_id),
                    "status": "passed"
                },
                "unsafe_ledger": {
                    "path": "validation/evidence/l2-slices/unsafe-ledger.json",
                    "status": "passed"
                }
            },
            "known_gaps": [
                "L2 test translation covers the named function slice and committed oracle fixture only.",
                "No full-project migration or exhaustive symbolic equivalence is claimed."
            ],
            "cache_invalidation_keys": [
                "schema_version",
                format!("source_commit={}", spec.source_commit),
                format!("fixture={}", relative_path(spec.fixture_path)),
                "cargo test --manifest-path validation/l2_slices/Cargo.toml",
                "emit_reports.rs"
            ]
        }),
    )
}

fn emit_l3_test_translation(spec: L3TestTranslationSpec<'_>) -> Result<(), Box<dyn Error>> {
    let slice_id = spec.slice_id;
    let prefix = format!("l3-{slice_id}");
    let rust_test = format!(
        "validation/l2_slices/tests/{slice_id}.rs::{}",
        spec.rust_test_name
    )
    .replace('-', "_");
    write_json(
        &spec
            .evidence_dir
            .join(format!("{prefix}-test-translation.json")),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": slice_id,
            "level": "L3",
            "status": "recorded",
            "source_commit": spec.source_commit,
            "repo_commit": "workspace",
            "source_test_inputs": {
                "oracle_strategy": "Committed C oracle fixture is replayed by Rust cargo tests and emit_reports evidence generation.",
                "fixtures": [{"path": relative_path(spec.fixture_path), "source_kind": "fixture"}],
                "oracle_reports": [{"path": format!("validation/evidence/demo/{prefix}-c-oracle.json"), "status": "passed"}]
            },
            "rust_tests": [
                {
                    "file": format!("validation/l2_slices/tests/{}.rs", slice_id.replace('-', "_")),
                    "test_names": [spec.rust_test_name],
                    "cargo_command": format!("cargo test --manifest-path validation/l2_slices/Cargo.toml --test {}", slice_id.replace('-', "_")),
                    "framework": "cargo test"
                }
            ],
            "coverage": {
                "main_paths": spec.main_paths,
                "error_paths": [],
                "negative_cases": spec.negative_cases
            },
            "translation_mappings": [
                {
                    "source": relative_path(spec.fixture_path),
                    "rust_test": rust_test,
                    "behavior_fields": spec.behavior_fields,
                    "coverage_kind": "main_path",
                    "status": "mapped"
                },
                {
                    "source": format!("validation/evidence/demo/{prefix}-negative-diff.json"),
                    "rust_test": format!("validation/l2_slices/src/bin/emit_reports.rs::emit_{}_negative_diff", slice_id.replace('-', "_")),
                    "behavior_fields": spec.behavior_fields,
                    "coverage_kind": "negative_case",
                    "status": "mapped"
                }
            ],
            "evidence_links": {
                "c_oracle": {"path": format!("validation/evidence/demo/{prefix}-c-oracle.json"), "status": "passed"},
                "rust_report": {"path": format!("validation/evidence/demo/{prefix}-rust-report.json"), "status": "passed"},
                "schema_diff": {"path": format!("validation/evidence/demo/{prefix}-diff.json"), "status": "passed"},
                "negative_diff": {"path": format!("validation/evidence/demo/{prefix}-negative-diff.json"), "status": "expected_failed"}
            },
            "known_gaps": [
                "L3 demo test translation covers the named function slice and committed oracle fixture only.",
                "No full-project migration or exhaustive symbolic equivalence is claimed."
            ]
        }),
    )
}

fn emit_call_expression_chain_test_translation(
    evidence_dir: &Path,
    fixture_path: &Path,
    case_count: usize,
) -> Result<(), Box<dyn Error>> {
    write_json(
        &evidence_dir.join("l3-call-expression-test-translation.json"),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "call-expression",
            "level": "L3",
            "status": "recorded",
            "source_commit": "demo-call-expression-20260625",
            "repo_commit": "workspace",
            "source_test_inputs": {
                "oracle_strategy": "Committed C oracle fixture is replayed by Rust cargo tests and emit_reports evidence generation.",
                "fixtures": [{"path": relative_path(fixture_path), "hash": "call-expression-fixture", "operation_count": case_count, "source_kind": "fixture"}],
                "oracle_reports": [
                    {"path": "validation/evidence/demo/l3-call-expression-c-oracle.json", "status": "passed"},
                    {"path": "validation/evidence/demo/l3-call-expression-rust-report.json", "status": "passed"}
                ]
            },
            "rust_tests": [
                {
                    "file": "validation/l2_slices/tests/call_expression_chain.rs",
                    "test_names": ["call_expression_chain_matches_c_oracle_and_records_call_contexts"],
                    "cargo_command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test call_expression_chain",
                    "framework": "cargo test"
                }
            ],
            "coverage": {
                "main_paths": [
                    "base negative/zero return path",
                    "recursive declaration initializer call",
                    "recursive assignment RHS call",
                    "recursive return expression call"
                ],
                "error_paths": [],
                "negative_cases": ["call expression metadata mutation rejected by negative diff"]
            },
            "translation_mappings": [
                {
                    "source": relative_path(fixture_path),
                    "rust_test": "validation/l2_slices/tests/call_expression_chain.rs::call_expression_chain_matches_c_oracle_and_records_call_contexts",
                    "behavior_fields": ["return_value", "status", "call_expression_count", "call_expression_contexts", "source_calls"],
                    "coverage_kind": "main_path",
                    "status": "mapped"
                },
                {
                    "source": "validation/evidence/demo/l3-call-expression-negative-diff.json",
                    "rust_test": "validation/l2_slices/src/bin/emit_reports.rs::emit_call_expression_chain_negative_diff",
                    "behavior_fields": ["call_expression_count", "call_expression_contexts"],
                    "coverage_kind": "negative_case",
                    "status": "mapped"
                }
            ],
            "evidence_links": {
                "c_oracle": {"path": "validation/evidence/demo/l3-call-expression-c-oracle.json", "status": "passed"},
                "rust_report": {"path": "validation/evidence/demo/l3-call-expression-rust-report.json", "status": "passed"},
                "schema_diff": {"path": "validation/evidence/demo/l3-call-expression-diff.json", "status": "passed"},
                "negative_diff": {"path": "validation/evidence/demo/l3-call-expression-negative-diff.json", "status": "expected_failed"},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-call-expression-unsafe-ledger.json", "status": "passed"}
            },
            "known_gaps": [
                "L3 demo test translation covers the named function slice and committed oracle fixture only.",
                "No external callee semantic proof, function pointer call support, nested call support, or full-project migration is claimed."
            ],
            "cache_invalidation_keys": [
                "source_commit",
                "repo_commit",
                "fixture.hash",
                "rust_boundary.module",
                "translator_version"
            ]
        }),
    )
}

fn emit_signed_rshift_contract_test_translation(
    evidence_dir: &Path,
    fixture_path: &Path,
    _case_count: usize,
) -> Result<(), Box<dyn Error>> {
    emit_l3_test_translation(L3TestTranslationSpec {
        evidence_dir,
        slice_id: "signed-rshift-contract",
        source_commit: "demo-signed-rshift-contract-20260628",
        fixture_path,
        rust_test_name: "signed_rshift_contract_matches_c_oracle_under_explicit_contract",
        main_paths: &[
            "positive signed right shift fixture cases",
            "negative arithmetic signed right shift fixture cases",
            "high valid shift-count fixture case",
        ],
        negative_cases: &[
            "contract mutation in negative diff",
            "missing explicit signed-right-shift contract is rejected by typed IR evidence tests",
        ],
        behavior_fields: &["return_value", "status", "contract"],
    })
}

fn emit_external_direct_callee_test_translation(
    evidence_dir: &Path,
    fixture_path: &Path,
    _case_count: usize,
) -> Result<(), Box<dyn Error>> {
    emit_l3_test_translation(L3TestTranslationSpec {
        evidence_dir,
        slice_id: "external-direct-callee",
        source_commit: "demo-external-direct-callee-20260625",
        fixture_path,
        rust_test_name: "external_direct_callee_matches_c_oracle_and_records_helper_context",
        main_paths: &[
            "external helper declaration initializer call",
            "external helper assignment RHS call",
            "external helper return expression call",
        ],
        negative_cases: &["external callee binding metadata mutation rejected by negative diff"],
        behavior_fields: &[
            "return_value",
            "status",
            "external_callee_call_count",
            "external_callee_contexts",
            "external_callee_bindings",
            "source_calls",
        ],
    })
}

fn emit_libuv_negative_diff(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("libuv-ip4-addr-c-oracle.json");
    let report: LibuvIp4OracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("libuv");
    let detected = write_libuv_negative_diff(&report, &evidence_dir)?;

    Ok(NegativeDiffResult {
        slice_id: "libuv-ip4-addr",
        status: if detected { "passed" } else { "failed" },
        report_path: "validation/evidence/libuv/l3-ip4-addr-negative-diff.json",
    })
}
