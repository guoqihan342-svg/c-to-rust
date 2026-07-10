fn write_real_fdb_is_str_negative_diff(
    report: &FdbIsStrOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .iter()
        .find(|case| case.id == "upper-exclusive-boundary")
        .ok_or("real-fdb-is-str fixture must include the 0x7f boundary case")?;
    let value = hex_to_bytes(&case.value_hex)?;
    let rust_value = replay_real_fdb_is_str(case)?;
    let mutated_c_value = value[..case.len].iter().copied().all(|byte| {
        u32::from(byte).wrapping_sub(u32::from(b' ')) <= u32::from(127u8 - b' ')
    });
    let detected = mutated_c_value != rust_value;
    write_json(
        &evidence_dir.join("l3-real-fdb-is-str-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": report.level,
            "target_id": report.target_id,
            "slice_id": report.slice_id,
            "source_commit": report.source_commit,
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "change the printable upper-bound comparison from < to <=",
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "return_value",
                    "mutated_c_value": mutated_c_value,
                    "rust_value": rust_value
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}

fn write_real_fdb_is_str_unsafe_ledger(
    repo_root: &Path,
    report: &FdbIsStrOracleReport,
    evidence_dir: &Path,
) -> Result<(), Box<dyn Error>> {
    let module_path = repo_root
        .join("validation")
        .join("l2_slices")
        .join("src")
        .join("fdb_is_str.rs");
    let source = fs::read_to_string(&module_path)?;
    let mut entries = Vec::new();
    for (index, line) in source.lines().enumerate() {
        let code = strip_strings_and_line_comments(line);
        if code
            .split(|ch: char| !(ch.is_ascii_alphanumeric() || ch == '_'))
            .any(|token| token == "unsafe")
        {
            entries.push(json!({
                "path": relative_path(&module_path),
                "line": index + 1,
                "text": code.trim()
            }));
        }
    }
    let status = if entries.is_empty() { "passed" } else { "failed" };
    write_json(
        &evidence_dir.join("l3-real-fdb-is-str-unsafe-ledger.json"),
        &json!({
            "schema_version": 1,
            "level": report.level,
            "target_id": report.target_id,
            "slice_id": report.slice_id,
            "source_commit": report.source_commit,
            "status": status,
            "scope": "first-party non-test Rust source for the named real-fdb-is-str reference module",
            "policy": {
                "first_party_non_test_unsafe_limit": 0,
                "registered_unsafe_required": true,
                "audit_required_even_when_zero": true
            },
            "first_party_non_test_unsafe_count": entries.len(),
            "entries": entries,
            "registered_unsafe": [],
            "introduced_unsafe": entries,
            "audit_status": status,
            "audited_modules": [relative_path(&module_path)]
        }),
    )
}
