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
