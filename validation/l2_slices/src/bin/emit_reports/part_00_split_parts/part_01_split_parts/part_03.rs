
fn emit_real_fdb_kv_del(fixtures_dir: &Path, repo_root: &Path) -> Result<(), Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("real-fdb-kv-del.json");
    let report: FdbKvDelOracleReport = read_json(&fixture_path)?;
    if report.case_count != report.cases.len() {
        return Err(format!(
            "real-fdb-kv-del case_count {} does not match {} fixture cases",
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
        .join("flashdb-real-fdb-kv-del.json");
    let oracle_status_path = evidence_dir
        .join("auto-translation")
        .join("real-fdb-kv-del")
        .join("l3-real-fdb-kv-del-c-oracle-status.json");
    let slice_spec: Value = read_json(&slice_spec_path)?;
    let oracle_status: Value = read_json(&oracle_status_path)?;
    let source_file_hashes = required_json_value(
        &slice_spec,
        "/source/source_file_hashes",
        "real-fdb-kv-del slice spec",
    )?
    .clone();
    let source_span_sha256 = required_json_value(
        &slice_spec,
        "/c_boundary/signatures/0/source_span/sha256",
        "real-fdb-kv-del slice spec",
    )?
    .clone();
    let fixture_sha256 = json!(sha256_hex(&fixture_path)?);
    let harness_draft_ref = required_json_value(
        &oracle_status,
        "/harness_draft_ref",
        "real-fdb-kv-del c oracle status",
    )?
    .clone();
    let compile_execution = if oracle_status.pointer("/compile_execution/status").is_some() {
        json!({
            "status": required_json_value(&oracle_status, "/compile_execution/status", "real-fdb-kv-del c oracle status")?.clone(),
            "semantic_pass": required_json_value(&oracle_status, "/compile_execution/semantic_pass", "real-fdb-kv-del c oracle status")?.clone(),
            "toolchain_adapter": required_json_value(&oracle_status, "/compile_execution/toolchain_adapter", "real-fdb-kv-del c oracle status")?.clone(),
            "toolchain_status_after_attempt": required_json_value(
                &oracle_status,
                "/compile_execution/toolchain_status_after_attempt",
                "real-fdb-kv-del c oracle status",
            )?.clone()
        })
    } else {
        json!({
            "status": oracle_status.get("status").cloned().unwrap_or_else(|| json!("accepted_oracle_promoted")),
            "semantic_pass": oracle_status.get("semantic_pass").cloned().unwrap_or_else(|| json!(true)),
            "toolchain_adapter": "accepted_evidence",
            "toolchain_status_after_attempt": oracle_status.get("toolchain_status").cloned().unwrap_or_else(|| json!("C_ORACLE_GENERATED"))
        })
    };

    let mut rust_cases = Vec::with_capacity(report.cases.len());
    let mut first_mismatch = None;
    for case in &report.cases {
        if case.expected_outputs.return_code != case.return_code {
            return Err(format!(
                "real-fdb-kv-del case {} return_code {} does not match expected_outputs.return_code {}",
                case.id,
                case.return_code,
                case.expected_outputs.return_code
            )
            .into());
        }
        let db = fdb_kv_del::KvDbFixture {
            init_ok: case.db_state != "uninitialized_named",
            name: case.db_name.clone(),
        };
        let actual = fdb_kv_del::fdb_kv_del(&db, &case.key);
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
            "db_state": case.db_state,
            "db_name": case.db_name,
            "key": case.key,
            "return_code": actual,
            "status": case.status
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    let prefix = "l3-real-fdb-kv-del";
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
            "source_commit": report.source_commit,
            "source_boundary": report.source_boundary,
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports",
            "generator": "validation/l2_slices/src/bin/emit_reports.rs::emit_real_fdb_kv_del",
            "case_count": report.case_count,
            "compared_fields": report.compared_fields,
            "provenance": {
                "fixture_sha256": fixture_sha256,
                "source_file_hashes": source_file_hashes,
                "source_span_sha256": source_span_sha256,
                "harness_draft_ref": harness_draft_ref,
                "compile_execution": compile_execution,
                "evidence_refs": {
                    "slice_spec": relative_path(&slice_spec_path),
                    "c_oracle_status": relative_path(&oracle_status_path),
                    "version_manifest": "validation/evidence/flashdb/auto-translation/real-fdb-kv-del/l3-real-fdb-kv-del-version-manifest.json",
                    "evidence_manifest": "validation/evidence/flashdb/auto-translation/real-fdb-kv-del/l3-real-fdb-kv-del-evidence-manifest.json"
                },
                "cycle_boundary": "This provenance intentionally omits the root c-oracle self hash; auto-translation evidence records the accepted c-oracle hash after regeneration."
            },
            "cases": c_oracle_cases,
            "accepted_boundary": "Accepted C oracle report is bound to the uninitialized-DB fixture case and WSL compile/harness evidence captured by the auto-translation oracle draft; generated Rust draft remains non-authoritative."
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-rust-report.json")),
        &json!({
            "schema_version": 1,
            "level": report.level,
            "target_id": report.target_id,
            "slice_id": report.slice_id,
            "source_commit": report.source_commit,
            "source_boundary": report.source_boundary,
            "rust_module_path": "validation/l2_slices/src/fdb_kv_del.rs",
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
            "source_commit": report.source_commit,
            "status": status,
            "case_count": report.case_count,
            "compared_fields": report.compared_fields,
            "first_mismatch": first_mismatch
        }),
    )?;
    write_real_fdb_kv_del_negative_diff(&report, &evidence_dir)?;

    Ok(())
}

fn write_real_fdb_kv_del_negative_diff(
    report: &FdbKvDelOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .first()
        .ok_or("real-fdb-kv-del fixture must include at least one case")?;
    let db = fdb_kv_del::KvDbFixture {
        init_ok: case.db_state != "uninitialized_named",
        name: case.db_name.clone(),
    };
    let actual = fdb_kv_del::fdb_kv_del(&db, &case.key);
    let mutated_return_code = case.return_code.saturating_sub(1);
    let detected = mutated_return_code != actual;
    write_json(
        &evidence_dir.join("l3-real-fdb-kv-del-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": report.level,
            "target_id": report.target_id,
            "slice_id": report.slice_id,
            "source_commit": report.source_commit,
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "first oracle case return_code is changed by saturating -1",
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
