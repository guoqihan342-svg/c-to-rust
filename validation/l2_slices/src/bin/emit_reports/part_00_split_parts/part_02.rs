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
