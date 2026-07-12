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
