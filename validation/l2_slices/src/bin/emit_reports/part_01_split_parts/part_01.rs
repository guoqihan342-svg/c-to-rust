fn emit_sum_i32_ptr_arith(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("sum-i32-ptr-arith-c-oracle.json");
    let oracle_value: Value = read_json(&fixture_path)?;
    let report: SumI32PtrArithOracleReport = serde_json::from_value(oracle_value.clone())?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    fs::create_dir_all(&evidence_dir)?;
    write_json(
        &evidence_dir.join("l3-sum-i32-ptr-arith-c-oracle.json"),
        &oracle_value,
    )?;

    let mut rust_cases = Vec::with_capacity(report.cases.len());
    let mut first_mismatch = None;

    for case in &report.cases {
        let rust = sum_i32_ptr_arith::sum_i32_ptr_arith(&case.values);
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
            "len",
            json!(case.len),
            json!(rust.len),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "sum",
            json!(case.sum),
            json!(rust.sum),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "source_reads",
            json!(case.source_reads),
            json!(rust.source_reads),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "canonical_reads",
            json!(case.canonical_reads),
            json!(rust.canonical_reads),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "source_write",
            json!(case.source_write),
            json!(rust.source_write),
        );

        rust_cases.push(json!({
            "id": case.id,
            "coverage_kind": case.coverage_kind,
            "values": case.values,
            "len": rust.len,
            "return_code": rust.return_code,
            "status": rust.status,
            "sum": rust.sum,
            "source_reads": rust.source_reads,
            "canonical_reads": rust.canonical_reads,
            "source_write": rust.source_write
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("l3-sum-i32-ptr-arith-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": "demo-sum-i32-ptr-arith-20260625",
            "c_source_boundary": "int sum_i32_ptr_arith(const int* values, int len, int* out) { int total = 0; for (int i = 0; i < len; i++) { total = total + *(values + i); } out[0] = total; return 0; }",
            "rust_module_path": "validation/l2_slices/src/sum_i32_ptr_arith.rs",
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --bin emit_reports",
            "status": status,
            "case_count": report.cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-ptr-arith-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": "demo-sum-i32-ptr-arith-20260625",
            "status": status,
            "case_count": report.cases.len(),
            "compared_fields": ["return_code", "status", "len", "sum", "source_reads", "canonical_reads", "source_write"],
            "first_mismatch": first_mismatch
        }),
    )?;
    emit_sum_i32_ptr_arith_performance_smoke(&report, &evidence_dir)?;

    Ok(SliceResult {
        slice_id: "demo-sum-i32-ptr-arith",
        case_count: report.cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_copy_i32_ptr_arith(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("copy-i32-ptr-arith-c-oracle.json");
    let oracle_value: Value = read_json(&fixture_path)?;
    let report: CopyI32PtrArithOracleReport = serde_json::from_value(oracle_value.clone())?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    fs::create_dir_all(&evidence_dir)?;
    write_json(
        &evidence_dir.join("l3-copy-i32-ptr-arith-c-oracle.json"),
        &oracle_value,
    )?;

    let mut rust_cases = Vec::with_capacity(report.cases.len());
    let mut first_mismatch = None;

    for case in &report.cases {
        let rust = copy_i32_ptr_arith::copy_i32_ptr_arith(&case.values);
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
            "len",
            json!(case.len),
            json!(rust.len),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "values",
            json!(case.values),
            json!(rust.values),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "out_values",
            json!(case.out_values),
            json!(rust.out_values),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "source_reads",
            json!(case.source_reads),
            json!(rust.source_reads),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "canonical_reads",
            json!(case.canonical_reads),
            json!(rust.canonical_reads),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "source_writes",
            json!(case.source_writes),
            json!(rust.source_writes),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "canonical_writes",
            json!(case.canonical_writes),
            json!(rust.canonical_writes),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "write_count",
            json!(case.write_count),
            json!(rust.write_count),
        );

        rust_cases.push(json!({
            "id": case.id,
            "coverage_kind": case.coverage_kind,
            "values": rust.values,
            "len": rust.len,
            "return_code": rust.return_code,
            "status": rust.status,
            "out_values": rust.out_values,
            "source_reads": rust.source_reads,
            "canonical_reads": rust.canonical_reads,
            "source_writes": rust.source_writes,
            "canonical_writes": rust.canonical_writes,
            "write_count": rust.write_count
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("l3-copy-i32-ptr-arith-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "copy-i32-ptr-arith",
            "source_commit": "demo-copy-i32-ptr-arith-20260625",
            "c_source_boundary": "int copy_i32_ptr_arith(const int* values, int len, int* out) { for (int i = 0; i < len; i++) { *(out + i) = *(values + i); } return 0; }",
            "rust_module_path": "validation/l2_slices/src/copy_i32_ptr_arith.rs",
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --bin emit_reports",
            "status": status,
            "case_count": report.cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-copy-i32-ptr-arith-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "copy-i32-ptr-arith",
            "source_commit": "demo-copy-i32-ptr-arith-20260625",
            "status": status,
            "case_count": report.cases.len(),
            "compared_fields": ["return_code", "status", "len", "values", "out_values", "source_reads", "canonical_reads", "source_writes", "canonical_writes", "write_count"],
            "first_mismatch": first_mismatch
        }),
    )?;
    emit_l3_test_translation(L3TestTranslationSpec {
        evidence_dir: &evidence_dir,
        slice_id: "copy-i32-ptr-arith",
        source_commit: "demo-copy-i32-ptr-arith-20260625",
        fixture_path: &fixture_path,
        rust_test_name: "copy_i32_ptr_arith_matches_c_oracle_with_safe_boundary",
        main_paths: &[
            "copy output buffer values",
            "raw/canonical pointer write evidence",
        ],
        negative_cases: &["negative diff mutates out_values"],
        behavior_fields: &[
            "return_code",
            "status",
            "len",
            "values",
            "out_values",
            "source_reads",
            "canonical_reads",
            "source_writes",
            "canonical_writes",
            "write_count",
        ],
    })?;
    emit_copy_i32_ptr_arith_performance_smoke(&report, &evidence_dir)?;

    Ok(SliceResult {
        slice_id: "demo-copy-i32-ptr-arith",
        case_count: report.cases.len(),
        l2_status: status,
        l3_status: status,
    })
}
