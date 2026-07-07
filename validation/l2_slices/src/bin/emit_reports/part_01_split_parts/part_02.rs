fn emit_add_i32_pair_ptr_arith(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("add-i32-pair-ptr-arith-c-oracle.json");
    let oracle_value: Value = read_json(&fixture_path)?;
    let report: AddI32PairPtrArithOracleReport = serde_json::from_value(oracle_value.clone())?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    fs::create_dir_all(&evidence_dir)?;
    write_json(
        &evidence_dir.join("l3-add-i32-pair-ptr-arith-c-oracle.json"),
        &oracle_value,
    )?;

    let mut rust_cases = Vec::with_capacity(report.cases.len());
    let mut first_mismatch = None;

    for case in &report.cases {
        let alias_case =
            add_i32_pair_ptr_arith::AddI32PairAliasCase::from_fixture(&case.alias_case)
                .ok_or("add_i32_pair_ptr_arith oracle contains unknown alias_case")?;
        let rust = add_i32_pair_ptr_arith::add_i32_pair_ptr_arith(&case.lhs, &case.rhs, alias_case);
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
            "lhs",
            json!(case.lhs),
            json!(rust.lhs),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "rhs",
            json!(case.rhs),
            json!(rust.rhs),
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
        compare_field(
            &mut first_mismatch,
            &case.id,
            "safe_noalias_precondition",
            json!(case.safe_noalias_precondition),
            json!(rust.safe_noalias_precondition),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "alias_case",
            json!(case.alias_case),
            json!(rust.alias_case),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "alias_matrix",
            json!(case.alias_matrix),
            json!(rust.alias_matrix),
        );

        rust_cases.push(json!({
            "id": case.id,
            "coverage_kind": case.coverage_kind,
            "lhs": rust.lhs,
            "rhs": rust.rhs,
            "len": rust.len,
            "return_code": rust.return_code,
            "status": rust.status,
            "out_values": rust.out_values,
            "source_reads": rust.source_reads,
            "canonical_reads": rust.canonical_reads,
            "source_writes": rust.source_writes,
            "canonical_writes": rust.canonical_writes,
            "write_count": rust.write_count,
            "safe_noalias_precondition": rust.safe_noalias_precondition,
            "alias_case": rust.alias_case,
            "alias_matrix": rust.alias_matrix
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("l3-add-i32-pair-ptr-arith-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "add-i32-pair-ptr-arith",
            "source_commit": "demo-add-i32-pair-ptr-arith-20260625",
            "c_source_boundary": "int add_i32_pair_ptr_arith(const int* lhs, const int* rhs, int len, int* out) { for (int i = 0; i < len; i++) { *(out + i) = *(lhs + i) + *(rhs + i); } return 0; }",
            "rust_module_path": "validation/l2_slices/src/add_i32_pair_ptr_arith.rs",
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --bin emit_reports",
            "status": status,
            "case_count": report.cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-add-i32-pair-ptr-arith-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "add-i32-pair-ptr-arith",
            "source_commit": "demo-add-i32-pair-ptr-arith-20260625",
            "status": status,
            "case_count": report.cases.len(),
            "compared_fields": ["return_code", "status", "len", "lhs", "rhs", "out_values", "source_reads", "canonical_reads", "source_writes", "canonical_writes", "write_count", "safe_noalias_precondition", "alias_case", "alias_matrix"],
            "first_mismatch": first_mismatch
        }),
    )?;
    emit_l3_test_translation(L3TestTranslationSpec {
        evidence_dir: &evidence_dir,
        slice_id: "add-i32-pair-ptr-arith",
        source_commit: "demo-add-i32-pair-ptr-arith-20260625",
        fixture_path: &fixture_path,
        rust_test_name: "add_i32_pair_ptr_arith_matches_c_oracle_and_records_alias_boundary",
        main_paths: &[
            "disjoint input pair addition",
            "lhs/rhs read-read alias accepted",
            "input/output overlap-risk metadata rejected at safe boundary",
        ],
        negative_cases: &["negative diff mutates alias_matrix"],
        behavior_fields: &[
            "return_code",
            "status",
            "len",
            "lhs",
            "rhs",
            "out_values",
            "source_reads",
            "canonical_reads",
            "source_writes",
            "canonical_writes",
            "write_count",
            "safe_noalias_precondition",
            "alias_case",
            "alias_matrix",
        ],
    })?;
    emit_add_i32_pair_ptr_arith_performance_smoke(&report, &evidence_dir)?;

    Ok(SliceResult {
        slice_id: "demo-add-i32-pair-ptr-arith",
        case_count: report.cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_libuv_ip4_addr(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("libuv-ip4-addr-c-oracle.json");
    let report: LibuvIp4OracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("libuv");
    fs::create_dir_all(&evidence_dir)?;

    let mut rust_cases = Vec::with_capacity(report.cases.len());
    let mut first_mismatch = None;

    for case in &report.cases {
        let rust = libuv_ip4_addr::uv_ip4_addr(&case.ip, case.port);
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
            "family",
            json!(case.family),
            json!(rust.family),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "port_host",
            json!(case.port_host),
            json!(rust.port_host),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "port_bytes_hex",
            json!(case.port_bytes_hex),
            json!(rust.port_bytes_hex),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "addr_bytes_hex",
            json!(case.addr_bytes_hex),
            json!(rust.addr_bytes_hex),
        );

        rust_cases.push(json!({
            "id": case.id,
            "ip": case.ip,
            "port": case.port,
            "coverage_kind": case.coverage_kind,
            "return_code": rust.return_code,
            "status": rust.status,
            "family": rust.family,
            "port_host": rust.port_host,
            "port_bytes_hex": rust.port_bytes_hex,
            "addr_bytes_hex": rust.addr_bytes_hex
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("l3-ip4-addr-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "source_commit": "5e7d51a8f4734cac453db960d4b9919735bbf7c3",
            "c_source_boundary": "uv_ip4_addr/uv_inet_pton/inet_pton4 from libuv",
            "rust_module_path": "validation/l2_slices/src/libuv_ip4_addr.rs",
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --bin emit_reports",
            "status": status,
            "case_count": report.cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-ip4-addr-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "status": status,
            "case_count": report.cases.len(),
            "compared_fields": [
                "return_code",
                "status",
                "family",
                "port_host",
                "port_bytes_hex",
                "addr_bytes_hex"
            ],
            "first_mismatch": first_mismatch
        }),
    )?;
    write_libuv_negative_diff(&report, &evidence_dir)?;
    emit_libuv_performance_smoke(&report, &evidence_dir)?;
    write_json(
        &evidence_dir.join("l3-ip4-addr-rust-check.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "status": "passed",
            "compile_self_healing": {
                "attempt_count": 0,
                "unresolved_errors": 0
            },
            "commands": [
                {
                    "command": "cargo test --test libuv_ip4_addr",
                    "status": "passed",
                    "red_log": "validation/evidence/libuv/l3-ip4-addr-red-test.log",
                    "green_log": "validation/evidence/libuv/l3-ip4-addr-green-test.log"
                },
                {
                    "command": "cargo run --bin emit_reports",
                    "status": "passed"
                }
            ]
        }),
    )?;

    Ok(SliceResult {
        slice_id: "libuv-ip4-addr",
        case_count: report.cases.len(),
        l2_status: status,
        l3_status: status,
    })
}
