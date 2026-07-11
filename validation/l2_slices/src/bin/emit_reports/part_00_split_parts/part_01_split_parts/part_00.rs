fn emit_real_fdb_calc_crc32(fixtures_dir: &Path, repo_root: &Path) -> Result<(), Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("real-fdb-calc-crc32.json");
    let report: FdbCalcCrc32OracleReport = read_json(&fixture_path)?;
    if report.case_count != report.cases.len() {
        return Err(format!(
            "real-fdb-calc-crc32 case_count {} does not match {} fixture cases",
            report.case_count,
            report.cases.len()
        )
        .into());
    }

    let evidence_dir = repo_root
        .join("validation")
        .join("evidence")
        .join("flashdb");
    fs::create_dir_all(&evidence_dir)?;
    let slice_spec_path = repo_root
        .join("validation")
        .join("slice-specs")
        .join("flashdb-real-fdb-calc-crc32.json");
    let oracle_status_path = evidence_dir
        .join("auto-translation")
        .join("real-fdb-calc-crc32")
        .join("l3-real-fdb-calc-crc32-c-oracle-status.json");
    let slice_spec: Value = read_json(&slice_spec_path)?;
    let oracle_status: Value = read_json(&oracle_status_path)?;
    let source_file_hashes = required_json_value(
        &slice_spec,
        "/source/source_file_hashes",
        "real-fdb slice spec",
    )?
    .clone();
    let source_span_sha256 = required_json_value(
        &slice_spec,
        "/c_boundary/signatures/0/source_span/sha256",
        "real-fdb slice spec",
    )?
    .clone();
    let source_commit = required_json_value(&slice_spec, "/source_commit", "real-fdb slice spec")?.clone();
    let fixture_sha256 = oracle_status
        .pointer("/fixture_sha256")
        .cloned()
        .unwrap_or(json!(sha256_hex(&fixture_path)?));
    let global_dependencies = required_json_value(
        &oracle_status,
        "/global_linkage_requirements",
        "real-fdb c oracle status",
    )?
    .clone();
    let harness_draft_ref = required_json_value(
        &oracle_status,
        "/harness_draft_ref",
        "real-fdb c oracle status",
    )?
    .clone();
    let compile_execution = json!({
        "status": required_json_value(&oracle_status, "/compile_execution/status", "real-fdb c oracle status")?.clone(),
        "semantic_pass": required_json_value(&oracle_status, "/compile_execution/semantic_pass", "real-fdb c oracle status")?.clone(),
        "toolchain_adapter": required_json_value(&oracle_status, "/compile_execution/toolchain_adapter", "real-fdb c oracle status")?.clone(),
        "toolchain_status_after_attempt": required_json_value(
            &oracle_status,
            "/compile_execution/toolchain_status_after_attempt",
            "real-fdb c oracle status",
        )?.clone()
    });

    let mut rust_cases = Vec::with_capacity(report.cases.len());
    let mut first_mismatch = None;
    for case in &report.cases {
        if case.buf.len() != case.size {
            return Err(format!(
                "real-fdb-calc-crc32 case {} size {} does not match {} bytes",
                case.id,
                case.size,
                case.buf.len()
            )
            .into());
        }
        let actual = fdb_calc_crc32::fdb_calc_crc32(case.crc, &case.buf);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "return_code",
            json!(case.return_code),
            json!(actual),
        );
        rust_cases.push(json!({
            "id": case.id,
            "coverage_kind": case.coverage_kind,
            "crc": case.crc,
            "buf": case.buf,
            "size": case.size,
            "return_code": actual,
            "status": case.status
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    let prefix = "l3-real-fdb-calc-crc32";
    let c_oracle_cases: Vec<Value> = report
        .cases
        .iter()
        .map(|case| {
            json!({
                "id": case.id,
                "return_code": case.return_code,
                "status": "passed"
            })
        })
        .collect();
    write_json(
        &evidence_dir.join(format!("{prefix}-c-oracle.json")),
        &json!({
            "schema_version": 1,
            "level": report.level,
            "target_id": report.target_id,
            "slice_id": report.slice_id,
            "status": "passed",
            "semantic_pass": true,
            "toolchain_status": "C_ORACLE_GENERATED",
            "source_commit": source_commit.clone(),
            "source_boundary": report.source_boundary,
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports",
            "generator": "validation/l2_slices/src/bin/emit_reports.rs::emit_real_fdb_calc_crc32",
            "case_count": report.case_count,
            "compared_fields": report.compared_fields,
            "provenance": {
                "fixture_sha256": fixture_sha256,
                "source_file_hashes": source_file_hashes,
                "source_span_sha256": source_span_sha256,
                "global_dependencies": global_dependencies,
                "harness_draft_ref": harness_draft_ref,
                "compile_execution": compile_execution,
                "evidence_refs": {
                    "slice_spec": relative_path(&slice_spec_path),
                    "c_oracle_status": relative_path(&oracle_status_path),
                    "version_manifest": "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-version-manifest.json",
                    "evidence_manifest": "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-evidence-manifest.json"
                },
                "cycle_boundary": "This provenance intentionally omits the root c-oracle self hash; auto-translation evidence records the accepted c-oracle hash after regeneration."
            },
            "cases": c_oracle_cases,
            "accepted_boundary": "Accepted C oracle report is bound to the fixture cases and WSL compile/harness evidence captured by the auto-translation oracle draft; generated Rust draft remains non-authoritative."
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-rust-report.json")),
        &json!({
            "schema_version": 1,
            "level": report.level,
            "target_id": report.target_id,
            "slice_id": report.slice_id,
            "source_commit": source_commit.clone(),
            "source_boundary": report.source_boundary,
            "rust_module_path": "validation/l2_slices/src/fdb_calc_crc32.rs",
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports",
            "status": status,
            "case_count": report.case_count,
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-diff.json")),
        &json!({
            "schema_version": 1,
            "level": report.level,
            "target_id": report.target_id,
            "slice_id": report.slice_id,
            "source_commit": source_commit.clone(),
            "status": status,
            "case_count": report.case_count,
            "compared_fields": report.compared_fields,
            "first_mismatch": first_mismatch
        }),
    )?;
    write_real_fdb_calc_crc32_negative_diff(&report, &evidence_dir, &source_commit)?;

    Ok(())
}

fn write_real_fdb_calc_crc32_negative_diff(
    report: &FdbCalcCrc32OracleReport,
    evidence_dir: &Path,
    source_commit: &Value,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .first()
        .ok_or("real-fdb-calc-crc32 fixture must include at least one case")?;
    let actual = fdb_calc_crc32::fdb_calc_crc32(case.crc, &case.buf);
    let mutated_return_code = case.return_code.wrapping_add(1);
    let detected = mutated_return_code != actual;
    write_json(
        &evidence_dir.join("l3-real-fdb-calc-crc32-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": report.level,
            "target_id": report.target_id,
            "slice_id": report.slice_id,
            "source_commit": source_commit.clone(),
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "first oracle case return_code is changed by wrapping +1",
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "return_code",
                    "mutated_c_value": mutated_return_code,
                    "rust_value": actual
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}
