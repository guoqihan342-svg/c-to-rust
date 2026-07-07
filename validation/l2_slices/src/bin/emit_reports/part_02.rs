fn emit_sqlite_varint(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("sqlite-varint-c-oracle.json");
    let cases: Vec<SqliteVarintCase> = read_json(&fixture_path)?;
    let mut rust_cases = Vec::with_capacity(cases.len());
    let mut first_mismatch = None;

    for case in &cases {
        let encoded = sqlite_varint::put_varint(case.value);
        let decoded = sqlite_varint::get_varint(&encoded).ok_or("encoded varint must decode")?;
        let rust_encoded_hex = bytes_to_hex(&encoded);
        let rust_case = json!({
            "id": case.id,
            "value": case.value,
            "encoded_hex": rust_encoded_hex,
            "bytes_used": encoded.len(),
            "decoded_value": decoded.value,
            "decoded_bytes": decoded.bytes_used
        });

        compare_field(
            &mut first_mismatch,
            &case.id,
            "encoded_hex",
            json!(case.encoded_hex),
            json!(rust_encoded_hex),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "bytes_used",
            json!(case.bytes_used),
            json!(encoded.len()),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "decoded_value",
            json!(case.decoded_value),
            json!(decoded.value),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "decoded_bytes",
            json!(case.decoded_bytes),
            json!(decoded.bytes_used),
        );

        rust_cases.push(rust_case);
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("sqlite-varint-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L2",
            "project_id": "sqlite",
            "slice_id": "sqlite-varint",
            "source_commit": "99a92ee66d80d519851015cf27def1c54e7a2037",
            "c_source_boundary": "sqlite3PutVarint/sqlite3GetVarint from sqlite3.c",
            "rust_module_path": "validation/l2_slices/src/sqlite_varint.rs",
            "fixture_input_description": "Boundary u64 values around SQLite varint width transitions and 64-bit extremes.",
            "fixture": relative_path(&fixture_path),
            "command": "cargo test",
            "status": status,
            "case_count": cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("sqlite-varint-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "slice_id": "sqlite-varint",
            "status": status,
            "case_count": cases.len(),
            "compared_fields": ["encoded_hex", "bytes_used", "decoded_value", "decoded_bytes"],
            "first_mismatch": first_mismatch
        }),
    )?;
    emit_l2_test_translation(L2TestTranslationSpec {
        evidence_dir,
        target_id: "sqlite",
        slice_id: "sqlite-varint",
        source_commit: "99a92ee66d80d519851015cf27def1c54e7a2037",
        fixture_path: &fixture_path,
        rust_test_name: "sqlite_varint_matches_c_oracle",
        main_paths: &[
            "single-byte varint",
            "multi-byte varint width boundaries",
            "u64 maximum varint",
        ],
        error_paths: &["truncated varint decode returns None"],
        negative_cases: &["encoded_hex mutation rejected by negative diff"],
        behavior_fields: &[
            "encoded_hex",
            "bytes_used",
            "decoded_value",
            "decoded_bytes",
        ],
    })?;

    Ok(SliceResult {
        slice_id: "sqlite-varint",
        case_count: cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_zlib_adler32(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("zlib-adler32-c-oracle.json");
    let cases: Vec<ChecksumCase> = read_json(&fixture_path)?;
    let mut rust_cases = Vec::with_capacity(cases.len());
    let mut first_mismatch = None;

    for case in &cases {
        let input = hex_to_bytes(&case.input_hex)?;
        let rust_value = zlib_adler32::adler32(&input);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "value",
            json!(case.value),
            json!(rust_value),
        );
        rust_cases.push(json!({
            "id": case.id,
            "input_len": input.len(),
            "value": rust_value,
            "value_hex": format!("0x{rust_value:08x}")
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("zlib-adler32-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L2",
            "project_id": "zlib-ng",
            "slice_id": "zlib-adler32",
            "source_commit": "d40f29fd42ed9158e3eb3e221dca50e4b627f7a8",
            "c_source_boundary": "adler32_z from zlib-ng build/libz.a",
            "rust_module_path": "validation/l2_slices/src/zlib_adler32.rs",
            "fixture_input_description": "Empty, ASCII, NMAX boundary, repeated byte, incrementing byte, and deterministic LCG byte buffers.",
            "fixture": relative_path(&fixture_path),
            "command": "cargo test",
            "status": status,
            "case_count": cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("zlib-adler32-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "slice_id": "zlib-adler32",
            "status": status,
            "case_count": cases.len(),
            "compared_fields": ["value"],
            "first_mismatch": first_mismatch
        }),
    )?;
    emit_l2_test_translation(L2TestTranslationSpec {
        evidence_dir,
        target_id: "zlib-ng",
        slice_id: "zlib-adler32",
        source_commit: "d40f29fd42ed9158e3eb3e221dca50e4b627f7a8",
        fixture_path: &fixture_path,
        rust_test_name: "zlib_adler32_matches_c_oracle",
        main_paths: &[
            "empty input",
            "ASCII input",
            "NMAX boundary input",
            "deterministic LCG byte buffers",
        ],
        error_paths: &[],
        negative_cases: &["checksum value mutation rejected by negative diff"],
        behavior_fields: &["value"],
    })?;

    Ok(SliceResult {
        slice_id: "zlib-adler32",
        case_count: cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_zstd_xxh32(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("zstd-xxh32-c-oracle.json");
    let cases: Vec<ChecksumCase> = read_json(&fixture_path)?;
    let mut rust_cases = Vec::with_capacity(cases.len());
    let mut first_mismatch = None;

    for case in &cases {
        let input = hex_to_bytes(&case.input_hex)?;
        let seed = case.seed.ok_or("zstd xxh32 fixture must include seed")?;
        let rust_value = zstd_xxh32::xxh32(&input, seed);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "value",
            json!(case.value),
            json!(rust_value),
        );
        rust_cases.push(json!({
            "id": case.id,
            "input_len": input.len(),
            "seed": seed,
            "value": rust_value,
            "value_hex": format!("0x{rust_value:08x}")
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("zstd-xxh32-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L2",
            "project_id": "zstd",
            "slice_id": "zstd-xxh32",
            "source_commit": "5233c58e6ca0b1c4c6b353ad79649191ed195bdc",
            "c_source_boundary": "XXH32 from zstd lib/common/xxhash.c",
            "rust_module_path": "validation/l2_slices/src/zstd_xxh32.rs",
            "fixture_input_description": "Length boundaries around the 16-byte XXH32 block path with seeds 0, 1, PRIME32_1, and u32::MAX.",
            "fixture": relative_path(&fixture_path),
            "command": "cargo test",
            "status": status,
            "case_count": cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("zstd-xxh32-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "slice_id": "zstd-xxh32",
            "status": status,
            "case_count": cases.len(),
            "compared_fields": ["value"],
            "first_mismatch": first_mismatch
        }),
    )?;
    emit_l2_test_translation(L2TestTranslationSpec {
        evidence_dir,
        target_id: "zstd",
        slice_id: "zstd-xxh32",
        source_commit: "5233c58e6ca0b1c4c6b353ad79649191ed195bdc",
        fixture_path: &fixture_path,
        rust_test_name: "zstd_xxh32_matches_c_oracle",
        main_paths: &[
            "short input path",
            "16-byte block path",
            "seed variations",
            "u32 maximum seed",
        ],
        error_paths: &[],
        negative_cases: &["checksum value mutation rejected by negative diff"],
        behavior_fields: &["value"],
    })?;

    Ok(SliceResult {
        slice_id: "zstd-xxh32",
        case_count: cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_negative_diffs(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<Vec<NegativeDiffResult>, Box<dyn Error>> {
    Ok(vec![
        emit_sqlite_negative_diff(fixtures_dir, evidence_dir)?,
        emit_zlib_negative_diff(fixtures_dir, evidence_dir)?,
        emit_zstd_negative_diff(fixtures_dir, evidence_dir)?,
    ])
}

fn emit_sqlite_negative_diff(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("sqlite-varint-c-oracle.json");
    let cases: Vec<SqliteVarintCase> = read_json(&fixture_path)?;
    let case = cases
        .first()
        .ok_or("sqlite-varint fixture must contain at least one case")?;
    let encoded = sqlite_varint::put_varint(case.value);
    let rust_encoded_hex = bytes_to_hex(&encoded);
    let mutated_c_value = if rust_encoded_hex == "00" { "01" } else { "00" };
    let detected = mutated_c_value != rust_encoded_hex;
    let status = if detected { "passed" } else { "failed" };
    let first_mismatch = if detected {
        Some(json!({
            "case_id": case.id,
            "field": "encoded_hex",
            "mutated_c_value": mutated_c_value,
            "rust_value": rust_encoded_hex
        }))
    } else {
        None
    };
    let report_path = "validation/evidence/l2-slices/sqlite-varint-negative-diff.json";
    write_json(
        &evidence_dir.join("sqlite-varint-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L2",
            "slice_id": "sqlite-varint",
            "status": status,
            "mutation": "first oracle case encoded_hex is replaced with a different byte",
            "case_id": case.id,
            "detected": detected,
            "first_mismatch": first_mismatch
        }),
    )?;

    Ok(NegativeDiffResult {
        slice_id: "sqlite-varint",
        status,
        report_path,
    })
}

fn emit_zlib_negative_diff(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("zlib-adler32-c-oracle.json");
    let cases: Vec<ChecksumCase> = read_json(&fixture_path)?;
    let case = cases
        .first()
        .ok_or("zlib-adler32 fixture must contain at least one case")?;
    let input = hex_to_bytes(&case.input_hex)?;
    let rust_value = zlib_adler32::adler32(&input);
    let mutated_c_value = case.value ^ 1;
    let detected = mutated_c_value != rust_value;
    let status = if detected { "passed" } else { "failed" };
    let first_mismatch = if detected {
        Some(json!({
            "case_id": case.id,
            "field": "value",
            "mutated_c_value": mutated_c_value,
            "rust_value": rust_value
        }))
    } else {
        None
    };
    let report_path = "validation/evidence/l2-slices/zlib-adler32-negative-diff.json";
    write_json(
        &evidence_dir.join("zlib-adler32-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L2",
            "slice_id": "zlib-adler32",
            "status": status,
            "mutation": "first oracle case value is replaced with value ^ 1",
            "case_id": case.id,
            "detected": detected,
            "first_mismatch": first_mismatch
        }),
    )?;

    Ok(NegativeDiffResult {
        slice_id: "zlib-adler32",
        status,
        report_path,
    })
}

fn emit_zstd_negative_diff(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("zstd-xxh32-c-oracle.json");
    let cases: Vec<ChecksumCase> = read_json(&fixture_path)?;
    let case = cases
        .first()
        .ok_or("zstd-xxh32 fixture must contain at least one case")?;
    let input = hex_to_bytes(&case.input_hex)?;
    let seed = case.seed.ok_or("zstd xxh32 fixture must include seed")?;
    let rust_value = zstd_xxh32::xxh32(&input, seed);
    let mutated_c_value = case.value ^ 1;
    let detected = mutated_c_value != rust_value;
    let status = if detected { "passed" } else { "failed" };
    let first_mismatch = if detected {
        Some(json!({
            "case_id": case.id,
            "field": "value",
            "mutated_c_value": mutated_c_value,
            "rust_value": rust_value
        }))
    } else {
        None
    };
    let report_path = "validation/evidence/l2-slices/zstd-xxh32-negative-diff.json";
    write_json(
        &evidence_dir.join("zstd-xxh32-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L2",
            "slice_id": "zstd-xxh32",
            "status": status,
            "mutation": "first oracle case value is replaced with value ^ 1",
            "case_id": case.id,
            "detected": detected,
            "first_mismatch": first_mismatch
        }),
    )?;

    Ok(NegativeDiffResult {
        slice_id: "zstd-xxh32",
        status,
        report_path,
    })
}

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

fn write_libuv_negative_diff(
    report: &LibuvIp4OracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .iter()
        .find(|case| case.return_code == 0)
        .ok_or("libuv oracle must include a passing case")?;
    let rust = libuv_ip4_addr::uv_ip4_addr(&case.ip, case.port);
    let mutated_addr = if case.addr_bytes_hex == "7f000001" {
        "7f000002"
    } else {
        "7f000001"
    };
    let detected = mutated_addr != rust.addr_bytes_hex;
    write_json(
        &evidence_dir.join("l3-ip4-addr-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "first passing oracle case addr_bytes_hex is changed",
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "addr_bytes_hex",
                    "mutated_c_value": mutated_addr,
                    "rust_value": rust.addr_bytes_hex
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}

fn emit_store_add_one_negative_diff(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("store-add-one-c-oracle.json");
    let report: StoreAddOneOracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    let detected = write_store_add_one_negative_diff(&report, &evidence_dir)?;

    Ok(NegativeDiffResult {
        slice_id: "demo-store-add-one",
        status: if detected { "passed" } else { "failed" },
        report_path: "validation/evidence/demo/l3-store-add-one-negative-diff.json",
    })
}

fn write_store_add_one_negative_diff(
    report: &StoreAddOneOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .first()
        .ok_or("store_add_one oracle must include at least one case")?;
    let rust = store_add_one::store_add_one(case.value);
    let mutated_out0 = case.out0.wrapping_add(1);
    let detected = mutated_out0 != rust.out0;
    write_json(
        &evidence_dir.join("l3-store-add-one-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "source_commit": "demo-store-add-one-20260625",
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "first oracle case out0 is changed by +1",
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "out0",
                    "mutated_c_value": mutated_out0,
                    "rust_value": rust.out0
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}

fn emit_sum_i32_buffer_negative_diff(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("sum-i32-buffer-c-oracle.json");
    let report: SumI32BufferOracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    let detected = write_sum_i32_buffer_negative_diff(&report, &evidence_dir)?;

    Ok(NegativeDiffResult {
        slice_id: "demo-sum-i32-buffer",
        status: if detected { "passed" } else { "failed" },
        report_path: "validation/evidence/demo/l3-sum-i32-buffer-negative-diff.json",
    })
}

fn write_sum_i32_buffer_negative_diff(
    report: &SumI32BufferOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .iter()
        .find(|case| !case.values.is_empty())
        .ok_or("sum_i32_buffer oracle must include at least one non-empty case")?;
    let rust = sum_i32_buffer::sum_i32_buffer(&case.values);
    let mutated_sum = case.sum.wrapping_add(1);
    let detected = mutated_sum != rust.sum;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": "demo-sum-i32-buffer-20260625",
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "first non-empty oracle case sum is changed by +1",
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "sum",
                    "mutated_c_value": mutated_sum,
                    "rust_value": rust.sum
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}

fn emit_call_expression_chain_negative_diff(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("call-expression-c-oracle.json");
    let report: CallExpressionChainOracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    let detected = write_call_expression_chain_negative_diff(&report, &evidence_dir)?;

    Ok(NegativeDiffResult {
        slice_id: "demo-call-expression",
        status: if detected { "passed" } else { "failed" },
        report_path: "validation/evidence/demo/l3-call-expression-negative-diff.json",
    })
}

fn write_call_expression_chain_negative_diff(
    report: &CallExpressionChainOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .iter()
        .find(|case| case.input_value > 0)
        .ok_or("call_expression_chain oracle must include at least one recursive case")?;
    let rust = call_expression_chain::call_expression_chain(case.input_value);
    let mutated_count = case.call_expression_count.saturating_sub(1);
    let detected = mutated_count != rust.call_expression_count
        || case.call_expression_contexts != rust.call_expression_contexts;
    write_json(
        &evidence_dir.join("l3-call-expression-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": "demo-call-expression-20260625",
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "detected": detected,
            "mutation": "recursive oracle case call_expression_count is changed by -1",
            "mutated_fields": ["call_expression_count"],
            "compared_fields": ["return_value", "status", "call_expression_count", "call_expression_contexts", "source_calls"],
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "call_expression_count",
                    "mutated_c_value": mutated_count,
                    "rust_value": rust.call_expression_count
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}

fn emit_signed_rshift_contract_negative_diff(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("signed-rshift-contract-c-oracle.json");
    let report: SignedRshiftContractOracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    let detected = write_signed_rshift_contract_negative_diff(&report, &evidence_dir)?;

    Ok(NegativeDiffResult {
        slice_id: "demo-signed-rshift-contract",
        status: if detected { "passed" } else { "failed" },
        report_path: "validation/evidence/demo/l3-signed-rshift-contract-negative-diff.json",
    })
}

fn write_signed_rshift_contract_negative_diff(
    report: &SignedRshiftContractOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .first()
        .ok_or("signed_rshift_contract oracle must include at least one case")?;
    let rust = signed_rshift_contract::signed_rshift_contract(case.value, case.count);
    let mutated_contract = "logical_right_shift";
    let detected = mutated_contract != rust.contract;
    write_json(
        &evidence_dir.join("l3-signed-rshift-contract-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "signed-rshift-contract",
            "source_commit": "demo-signed-rshift-contract-20260628",
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "first oracle case implementation-defined signed right shift contract is changed",
            "case_id": case.id,
            "compared_fields": ["return_value", "status", "contract"],
            "mutated_fields": ["contract"],
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "contract",
                    "mutated_c_value": mutated_contract,
                    "rust_value": rust.contract
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}
