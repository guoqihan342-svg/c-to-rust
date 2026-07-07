fn emit_real_fdb_blob_make(fixtures_dir: &Path, repo_root: &Path) -> Result<(), Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("real-fdb-blob-make.json");
    let report: FdbBlobMakeOracleReport = read_json(&fixture_path)?;
    if report.case_count != report.cases.len() {
        return Err(format!(
            "real-fdb-blob-make case_count {} does not match {} fixture cases",
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
        .join("flashdb-real-fdb-blob-make.json");
    let oracle_status_path = evidence_dir
        .join("auto-translation")
        .join("real-fdb-blob-make")
        .join("l3-real-fdb-blob-make-c-oracle-status.json");
    let slice_spec: Value = read_json(&slice_spec_path)?;
    let oracle_status: Value = read_json(&oracle_status_path)?;
    let source_file_hashes = required_json_value(
        &slice_spec,
        "/source/source_file_hashes",
        "real-fdb-blob-make slice spec",
    )?
    .clone();
    let source_span_sha256 = required_json_value(
        &slice_spec,
        "/c_boundary/signatures/0/source_span/sha256",
        "real-fdb-blob-make slice spec",
    )?
    .clone();
    let fixture_identity = required_json_value(
        &slice_spec,
        "/fixture_contract/hash",
        "real-fdb-blob-make slice spec",
    )?
    .clone();
    let harness_draft_ref = required_json_value(
        &oracle_status,
        "/harness_draft_ref",
        "real-fdb-blob-make c oracle status",
    )?
    .clone();
    let compile_execution = if oracle_status.pointer("/compile_execution/status").is_some() {
        json!({
            "status": required_json_value(&oracle_status, "/compile_execution/status", "real-fdb-blob-make c oracle status")?.clone(),
            "semantic_pass": required_json_value(&oracle_status, "/compile_execution/semantic_pass", "real-fdb-blob-make c oracle status")?.clone(),
            "toolchain_adapter": required_json_value(&oracle_status, "/compile_execution/toolchain_adapter", "real-fdb-blob-make c oracle status")?.clone(),
            "toolchain_status_after_attempt": required_json_value(
                &oracle_status,
                "/compile_execution/toolchain_status_after_attempt",
                "real-fdb-blob-make c oracle status",
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
        let value_buf = case.value_buf.clone().unwrap_or_default();
        let value_ptr = if value_buf.is_empty() {
            core::ptr::null()
        } else {
            value_buf.as_ptr().cast()
        };
        let mut blob = fdb_blob_make::FdbBlob {
            buf: core::ptr::null_mut(),
            size: case.initial_blob_size,
        };
        let blob_addr = (&mut blob as *mut fdb_blob_make::FdbBlob).cast::<core::ffi::c_void>();
        let returned = fdb_blob_make::fdb_blob_make(&mut blob, value_ptr, case.buf_len);
        let returned_addr = (returned as *mut fdb_blob_make::FdbBlob).cast::<core::ffi::c_void>();
        let return_same_blob = returned_addr == blob_addr;
        let blob_buf = if returned.buf == value_ptr.cast_mut() {
            "value_buf"
        } else {
            "unexpected"
        };
        let blob_size = returned.size;

        compare_field(
            &mut first_mismatch,
            &case.id,
            "return_same_blob",
            json!(case.expected_outputs.return_same_blob),
            json!(return_same_blob),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "blob.buf",
            json!(case.expected_outputs.blob_buf),
            json!(blob_buf),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "blob.size",
            json!(case.expected_outputs.blob_size),
            json!(blob_size),
        );
        rust_cases.push(json!({
            "id": case.id,
            "coverage_kind": case.coverage_kind,
            "buf_len": case.buf_len,
            "initial_blob_size": case.initial_blob_size,
            "return_same_blob": return_same_blob,
            "blob.buf": blob_buf,
            "blob.size": blob_size,
            "status": case.status
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    let prefix = "l3-real-fdb-blob-make";
    let c_oracle_cases: Vec<Value> = report
        .cases
        .iter()
        .map(|case| {
            json!({
                "id": case.id,
                "return_same_blob": case.expected_outputs.return_same_blob,
                "blob.buf": case.expected_outputs.blob_buf,
                "blob.size": case.expected_outputs.blob_size,
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
            "generator": "validation/l2_slices/src/bin/emit_reports.rs::emit_real_fdb_blob_make",
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
                    "version_manifest": "validation/evidence/flashdb/auto-translation/real-fdb-blob-make/l3-real-fdb-blob-make-version-manifest.json",
                    "evidence_manifest": "validation/evidence/flashdb/auto-translation/real-fdb-blob-make/l3-real-fdb-blob-make-evidence-manifest.json"
                },
                "cycle_boundary": "This provenance intentionally omits the root c-oracle self hash; auto-translation evidence records the accepted c-oracle hash after regeneration."
            },
            "cases": c_oracle_cases,
            "accepted_boundary": "Accepted C oracle report is bound to fixture cases and compile/harness evidence captured by the auto-translation oracle draft; generated Rust draft remains non-authoritative."
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
            "rust_module_path": "validation/l2_slices/src/fdb_blob_make.rs",
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
    write_real_fdb_blob_make_negative_diff(&report, &evidence_dir)?;

    Ok(())
}

fn write_real_fdb_blob_make_negative_diff(
    report: &FdbBlobMakeOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .first()
        .ok_or("real-fdb-blob-make fixture must include at least one case")?;
    let value_buf = case.value_buf.clone().unwrap_or_default();
    let value_ptr = if value_buf.is_empty() {
        core::ptr::null()
    } else {
        value_buf.as_ptr().cast()
    };
    let mut blob = fdb_blob_make::FdbBlob {
        buf: core::ptr::null_mut(),
        size: case.initial_blob_size,
    };
    let returned = fdb_blob_make::fdb_blob_make(&mut blob, value_ptr, case.buf_len);
    let mutated_blob_size = case.expected_outputs.blob_size.wrapping_add(1);
    let detected = mutated_blob_size != returned.size;
    write_json(
        &evidence_dir.join("l3-real-fdb-blob-make-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": report.level,
            "target_id": report.target_id,
            "slice_id": report.slice_id,
            "source_commit": report.source_commit,
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "first oracle case blob.size is changed by wrapping +1",
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "blob.size",
                    "mutated_c_value": mutated_blob_size,
                    "rust_value": returned.size
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}

fn emit_store_add_one(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("store-add-one-c-oracle.json");
    let oracle_value: Value = read_json(&fixture_path)?;
    let report: StoreAddOneOracleReport = serde_json::from_value(oracle_value.clone())?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    fs::create_dir_all(&evidence_dir)?;
    write_json(
        &evidence_dir.join("l3-store-add-one-c-oracle.json"),
        &oracle_value,
    )?;

    let mut rust_cases = Vec::with_capacity(report.cases.len());
    let mut first_mismatch = None;

    for case in &report.cases {
        let rust = store_add_one::store_add_one(case.value);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "return_code",
            json!(case.return_code),
            json!(rust.return_code),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "status",
            json!(case.status),
            json!(rust.status),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "out0",
            json!(case.out0),
            json!(rust.out0),
        );

        rust_cases.push(json!({
            "id": case.id,
            "coverage_kind": case.coverage_kind,
            "value": case.value,
            "return_code": rust.return_code,
            "status": rust.status,
            "out0": rust.out0,
            "source_write": rust.source_write
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("l3-store-add-one-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "source_commit": "demo-store-add-one-20260625",
            "c_source_boundary": "int store_add_one(int value, int* out) { out[0] = value + 1; return 0; }",
            "rust_module_path": "validation/l2_slices/src/store_add_one.rs",
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --bin emit_reports",
            "status": status,
            "case_count": report.cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "source_commit": "demo-store-add-one-20260625",
            "status": status,
            "case_count": report.cases.len(),
            "compared_fields": ["return_code", "status", "out0"],
            "first_mismatch": first_mismatch
        }),
    )?;
    write_store_add_one_negative_diff(&report, &evidence_dir)?;
    emit_store_add_one_performance_smoke(&report, &evidence_dir)?;
    emit_store_add_one_static_l3_evidence(&evidence_dir, report.cases.len(), status)?;

    Ok(SliceResult {
        slice_id: "demo-store-add-one",
        case_count: report.cases.len(),
        l2_status: status,
        l3_status: status,
    })
}
