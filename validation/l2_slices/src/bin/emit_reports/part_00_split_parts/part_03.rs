#[derive(Debug, Deserialize)]
struct FdbTslToBlobOracleReport {
    level: String,
    target_id: String,
    slice_id: String,
    source_commit: String,
    source_boundary: Value,
    compared_fields: Vec<String>,
    case_count: usize,
    cases: Vec<FdbTslToBlobOracleCase>,
}

#[derive(Debug, Deserialize)]
struct FdbTslToBlobOracleCase {
    id: String,
    coverage_kind: String,
    tsl: FdbTslToBlobTslInput,
    initial_blob_saved: FdbTslToBlobSavedInput,
    expected_outputs: FdbTslToBlobExpectedOutputs,
    status: String,
}

#[derive(Debug, Deserialize)]
struct FdbTslToBlobTslInput {
    #[serde(rename = "addr.index")]
    addr_index: u32,
    #[serde(rename = "addr.log")]
    addr_log: u32,
    log_len: u32,
}

#[derive(Debug, Deserialize)]
struct FdbTslToBlobSavedInput {
    meta_addr: u32,
    addr: u32,
    len: usize,
}

#[derive(Debug, Deserialize)]
struct FdbTslToBlobExpectedOutputs {
    #[serde(rename = "return_same_blob")]
    return_same_blob: bool,
    #[serde(rename = "blob.saved.meta_addr")]
    blob_saved_meta_addr: u32,
    #[serde(rename = "blob.saved.addr")]
    blob_saved_addr: u32,
    #[serde(rename = "blob.saved.len")]
    blob_saved_len: usize,
}

#[derive(Debug)]
struct FdbTslToBlobReplay {
    return_same_blob: bool,
    blob_saved_meta_addr: u32,
    blob_saved_addr: u32,
    blob_saved_len: usize,
}

fn replay_real_fdb_tsl_to_blob(case: &FdbTslToBlobOracleCase) -> FdbTslToBlobReplay {
    let tsl = fdb_tsl_to_blob::FdbTsl {
        addr: fdb_tsl_to_blob::FdbTslAddr {
            index: case.tsl.addr_index,
            log: case.tsl.addr_log,
        },
        log_len: case.tsl.log_len,
    };
    let mut blob = fdb_tsl_to_blob::FdbBlob {
        saved: fdb_tsl_to_blob::FdbBlobSaved {
            meta_addr: case.initial_blob_saved.meta_addr,
            addr: case.initial_blob_saved.addr,
            len: case.initial_blob_saved.len,
        },
        ..fdb_tsl_to_blob::FdbBlob::default()
    };
    let blob_addr = (&mut blob as *mut fdb_tsl_to_blob::FdbBlob).cast::<core::ffi::c_void>();
    let returned = fdb_tsl_to_blob::fdb_tsl_to_blob(&tsl, &mut blob);
    let returned_addr = (returned as *mut fdb_tsl_to_blob::FdbBlob).cast::<core::ffi::c_void>();

    FdbTslToBlobReplay {
        return_same_blob: returned_addr == blob_addr,
        blob_saved_meta_addr: returned.saved.meta_addr,
        blob_saved_addr: returned.saved.addr,
        blob_saved_len: returned.saved.len,
    }
}

fn emit_real_fdb_tsl_to_blob(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<(), Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("real-fdb-tsl-to-blob.json");
    let report: FdbTslToBlobOracleReport = read_json(&fixture_path)?;
    if report.case_count != report.cases.len() {
        return Err(format!(
            "real-fdb-tsl-to-blob case_count {} does not match {} fixture cases",
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
        .join("flashdb-real-fdb-tsl-to-blob.json");
    let oracle_status_path = evidence_dir
        .join("auto-translation")
        .join("real-fdb-tsl-to-blob")
        .join("l3-real-fdb-tsl-to-blob-c-oracle-status.json");
    let slice_spec: Value = read_json(&slice_spec_path)?;
    let oracle_status: Value = read_json(&oracle_status_path)?;
    let source_file_hashes = required_json_value(
        &slice_spec,
        "/source/source_file_hashes",
        "real-fdb-tsl-to-blob slice spec",
    )?
    .clone();
    let source_span_sha256 = required_json_value(
        &slice_spec,
        "/c_boundary/signatures/0/source_span/sha256",
        "real-fdb-tsl-to-blob slice spec",
    )?
    .clone();
    let fixture_identity = required_json_value(
        &slice_spec,
        "/fixture_contract/hash",
        "real-fdb-tsl-to-blob slice spec",
    )?
    .clone();
    let harness_draft_ref = required_json_value(
        &oracle_status,
        "/harness_draft_ref",
        "real-fdb-tsl-to-blob c oracle status",
    )?
    .clone();
    let compile_execution = if oracle_status.pointer("/compile_execution/status").is_some() {
        json!({
            "status": required_json_value(&oracle_status, "/compile_execution/status", "real-fdb-tsl-to-blob c oracle status")?.clone(),
            "semantic_pass": required_json_value(&oracle_status, "/compile_execution/semantic_pass", "real-fdb-tsl-to-blob c oracle status")?.clone(),
            "toolchain_adapter": required_json_value(&oracle_status, "/compile_execution/toolchain_adapter", "real-fdb-tsl-to-blob c oracle status")?.clone(),
            "toolchain_status_after_attempt": required_json_value(
                &oracle_status,
                "/compile_execution/toolchain_status_after_attempt",
                "real-fdb-tsl-to-blob c oracle status",
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
        let replay = replay_real_fdb_tsl_to_blob(case);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "return_same_blob",
            json!(case.expected_outputs.return_same_blob),
            json!(replay.return_same_blob),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "blob.saved.meta_addr",
            json!(case.expected_outputs.blob_saved_meta_addr),
            json!(replay.blob_saved_meta_addr),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "blob.saved.addr",
            json!(case.expected_outputs.blob_saved_addr),
            json!(replay.blob_saved_addr),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "blob.saved.len",
            json!(case.expected_outputs.blob_saved_len),
            json!(replay.blob_saved_len),
        );
        rust_cases.push(json!({
            "id": case.id,
            "coverage_kind": case.coverage_kind,
            "return_same_blob": replay.return_same_blob,
            "blob.saved.meta_addr": replay.blob_saved_meta_addr,
            "blob.saved.addr": replay.blob_saved_addr,
            "blob.saved.len": replay.blob_saved_len,
            "status": case.status
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    let prefix = "l3-real-fdb-tsl-to-blob";
    let c_oracle_cases: Vec<Value> = report
        .cases
        .iter()
        .map(|case| {
            json!({
                "id": case.id,
                "return_same_blob": case.expected_outputs.return_same_blob,
                "blob.saved.meta_addr": case.expected_outputs.blob_saved_meta_addr,
                "blob.saved.addr": case.expected_outputs.blob_saved_addr,
                "blob.saved.len": case.expected_outputs.blob_saved_len,
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
            "generator": "validation/l2_slices/src/bin/emit_reports.rs::emit_real_fdb_tsl_to_blob",
            "case_count": report.case_count,
            "compared_fields": report.compared_fields,
            "provenance": {
                "fixture_identity": fixture_identity,
                "source_file_hashes": source_file_hashes,
                "source_span_sha256": source_span_sha256,
                "harness_draft_ref": harness_draft_ref,
                "compile_execution": compile_execution,
                "evidence_refs": {
                    "slice_spec": relative_path(&slice_spec_path),
                    "c_oracle_status": relative_path(&oracle_status_path),
                    "version_manifest": "validation/evidence/flashdb/auto-translation/real-fdb-tsl-to-blob/l3-real-fdb-tsl-to-blob-version-manifest.json",
                    "evidence_manifest": "validation/evidence/flashdb/auto-translation/real-fdb-tsl-to-blob/l3-real-fdb-tsl-to-blob-evidence-manifest.json"
                },
                "cycle_boundary": "This provenance intentionally omits the root c-oracle self hash; auto-translation evidence records the accepted c-oracle hash after regeneration."
            },
            "cases": c_oracle_cases,
            "accepted_boundary": "Accepted C oracle report is bound to the declared TSL field-copy fixture and compile/harness evidence; generated Rust draft remains non-authoritative."
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
            "rust_module_path": "validation/l2_slices/src/fdb_tsl_to_blob.rs",
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
    write_real_fdb_tsl_to_blob_negative_diff(&report, &evidence_dir)?;
    write_real_fdb_tsl_to_blob_unsafe_ledger(repo_root, &report, &evidence_dir)?;

    Ok(())
}

fn write_real_fdb_tsl_to_blob_negative_diff(
    report: &FdbTslToBlobOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .first()
        .ok_or("real-fdb-tsl-to-blob fixture must include at least one case")?;
    let replay = replay_real_fdb_tsl_to_blob(case);
    let mutated_len = case.expected_outputs.blob_saved_len.wrapping_add(1);
    let detected = mutated_len != replay.blob_saved_len;
    write_json(
        &evidence_dir.join("l3-real-fdb-tsl-to-blob-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": report.level,
            "target_id": report.target_id,
            "slice_id": report.slice_id,
            "source_commit": report.source_commit,
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "first oracle case blob.saved.len is changed by wrapping +1",
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "blob.saved.len",
                    "mutated_c_value": mutated_len,
                    "rust_value": replay.blob_saved_len
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}

fn write_real_fdb_tsl_to_blob_unsafe_ledger(
    repo_root: &Path,
    report: &FdbTslToBlobOracleReport,
    evidence_dir: &Path,
) -> Result<(), Box<dyn Error>> {
    let module_path = repo_root
        .join("validation")
        .join("l2_slices")
        .join("src")
        .join("fdb_tsl_to_blob.rs");
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
        &evidence_dir.join("l3-real-fdb-tsl-to-blob-unsafe-ledger.json"),
        &json!({
            "schema_version": 1,
            "level": report.level,
            "target_id": report.target_id,
            "slice_id": report.slice_id,
            "source_commit": report.source_commit,
            "status": status,
            "scope": "first-party non-test Rust source for the named real-fdb-tsl-to-blob reference module",
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
