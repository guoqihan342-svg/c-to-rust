fn emit_external_direct_callee_negative_diff(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("external-direct-callee-c-oracle.json");
    let report: ExternalDirectCalleeOracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    let detected = write_external_direct_callee_negative_diff(&report, &evidence_dir)?;

    Ok(NegativeDiffResult {
        slice_id: "demo-external-direct-callee",
        status: if detected { "passed" } else { "failed" },
        report_path: "validation/evidence/demo/l3-external-direct-callee-negative-diff.json",
    })
}

fn write_external_direct_callee_negative_diff(
    report: &ExternalDirectCalleeOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .iter()
        .next()
        .ok_or("external_direct_callee oracle must include at least one case")?;
    let rust = external_direct_callee::call_helper_chain(case.input_value);
    let mutated_count = case.external_callee_call_count.saturating_sub(1);
    let detected = mutated_count != rust.external_callee_call_count
        || case.external_callee_bindings != rust.external_callee_bindings;
    write_json(
        &evidence_dir.join("l3-external-direct-callee-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "external-direct-callee",
            "source_commit": "demo-external-direct-callee-20260625",
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "detected": detected,
            "mutation": "external direct callee call count is changed by -1",
            "mutated_fields": ["external_callee_call_count"],
            "compared_fields": ["return_value", "status", "external_callee_call_count", "external_callee_contexts", "external_callee_bindings", "source_calls"],
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "external_callee_call_count",
                    "mutated_c_value": mutated_count,
                    "rust_value": rust.external_callee_call_count
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}

fn emit_sum_i32_ptr_arith_negative_diff(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("sum-i32-ptr-arith-c-oracle.json");
    let report: SumI32PtrArithOracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    let detected = write_sum_i32_ptr_arith_negative_diff(&report, &evidence_dir)?;

    Ok(NegativeDiffResult {
        slice_id: "demo-sum-i32-ptr-arith",
        status: if detected { "passed" } else { "failed" },
        report_path: "validation/evidence/demo/l3-sum-i32-ptr-arith-negative-diff.json",
    })
}

fn write_sum_i32_ptr_arith_negative_diff(
    report: &SumI32PtrArithOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .iter()
        .find(|case| !case.values.is_empty())
        .ok_or("sum_i32_ptr_arith oracle must include at least one non-empty case")?;
    let rust = sum_i32_ptr_arith::sum_i32_ptr_arith(&case.values);
    let mutated_sum = case.sum.wrapping_add(1);
    let detected = mutated_sum != rust.sum;
    write_json(
        &evidence_dir.join("l3-sum-i32-ptr-arith-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": "demo-sum-i32-ptr-arith-20260625",
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "first non-empty oracle case sum is changed by +1",
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "sum",
                    "mutated_c_value": mutated_sum,
                    "rust_value": rust.sum
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}

fn emit_copy_i32_ptr_arith_negative_diff(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("copy-i32-ptr-arith-c-oracle.json");
    let report: CopyI32PtrArithOracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    let detected = write_copy_i32_ptr_arith_negative_diff(&report, &evidence_dir)?;

    Ok(NegativeDiffResult {
        slice_id: "demo-copy-i32-ptr-arith",
        status: if detected { "passed" } else { "failed" },
        report_path: "validation/evidence/demo/l3-copy-i32-ptr-arith-negative-diff.json",
    })
}

fn write_copy_i32_ptr_arith_negative_diff(
    report: &CopyI32PtrArithOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .iter()
        .find(|case| !case.out_values.is_empty())
        .ok_or("copy_i32_ptr_arith oracle must include at least one non-empty case")?;
    let rust = copy_i32_ptr_arith::copy_i32_ptr_arith(&case.values);
    let mut mutated_out_values = case.out_values.clone();
    mutated_out_values[0] = mutated_out_values[0].wrapping_add(1);
    let detected = mutated_out_values != rust.out_values;
    write_json(
        &evidence_dir.join("l3-copy-i32-ptr-arith-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "copy-i32-ptr-arith",
            "source_commit": "demo-copy-i32-ptr-arith-20260625",
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "first non-empty oracle case out_values[0] is changed by +1",
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "out_values",
                    "mutated_c_value": mutated_out_values,
                    "rust_value": rust.out_values
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}

fn emit_add_i32_pair_ptr_arith_negative_diff(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("add-i32-pair-ptr-arith-c-oracle.json");
    let report: AddI32PairPtrArithOracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    let detected = write_add_i32_pair_ptr_arith_negative_diff(&report, &evidence_dir)?;

    Ok(NegativeDiffResult {
        slice_id: "demo-add-i32-pair-ptr-arith",
        status: if detected { "passed" } else { "failed" },
        report_path: "validation/evidence/demo/l3-add-i32-pair-ptr-arith-negative-diff.json",
    })
}

fn write_add_i32_pair_ptr_arith_negative_diff(
    report: &AddI32PairPtrArithOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .iter()
        .find(|case| case.alias_case == "lhs_rhs_read_alias")
        .ok_or("add_i32_pair_ptr_arith oracle must include lhs/rhs read alias case")?;
    let alias_case = add_i32_pair_ptr_arith::AddI32PairAliasCase::from_fixture(&case.alias_case)
        .ok_or("add_i32_pair_ptr_arith oracle contains unknown alias_case")?;
    let rust = add_i32_pair_ptr_arith::add_i32_pair_ptr_arith(&case.lhs, &case.rhs, alias_case);
    let mut mutated_alias_matrix = case.alias_matrix.clone();
    if let Some(first) = mutated_alias_matrix.first_mut() {
        *first = "lhs-rhs:disjoint".to_owned();
    }
    let detected = mutated_alias_matrix != rust.alias_matrix;
    write_json(
        &evidence_dir.join("l3-add-i32-pair-ptr-arith-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "add-i32-pair-ptr-arith",
            "source_commit": "demo-add-i32-pair-ptr-arith-20260625",
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "lhs/rhs read alias case alias_matrix[0] is changed to disjoint",
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "alias_matrix",
                    "mutated_c_value": mutated_alias_matrix,
                    "rust_value": rust.alias_matrix
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}

fn emit_libuv_performance_smoke(
    report: &LibuvIp4OracleReport,
    evidence_dir: &Path,
) -> Result<(), Box<dyn Error>> {
    let iterations = PERFORMANCE_SMOKE_ITERATIONS;
    let mut calls = 0_u64;
    for _ in 0..iterations {
        for case in &report.cases {
            let _ = libuv_ip4_addr::uv_ip4_addr(&case.ip, case.port);
            calls += 1;
        }
    }
    write_json(
        &evidence_dir.join("l3-ip4-addr-performance-smoke.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "status": "recorded",
            "secondary_only": true,
            "operation": "safe Rust uv_ip4_addr replay over fixture corpus",
            "iterations": iterations,
            "calls": calls,
            "elapsed_ms": 0.0,
            "elapsed_boundary": "Deterministic report refresh records call count; wall-clock step duration is recorded by full regression logs.",
            "reporting_boundary": "Performance smoke is secondary evidence only and does not replace correctness gates."
        }),
    )
}

fn emit_store_add_one_performance_smoke(
    report: &StoreAddOneOracleReport,
    evidence_dir: &Path,
) -> Result<(), Box<dyn Error>> {
    let iterations = PERFORMANCE_SMOKE_ITERATIONS;
    let mut calls = 0_u64;
    for _ in 0..iterations {
        for case in &report.cases {
            let _ = store_add_one::store_add_one(case.value);
            calls += 1;
        }
    }
    write_json(
        &evidence_dir.join("l3-store-add-one-performance-smoke.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "source_commit": "demo-store-add-one-20260625",
            "status": "recorded",
            "secondary_only": true,
            "operation": "safe Rust store_add_one replay over fixture corpus",
            "iterations": iterations,
            "calls": calls,
            "elapsed_ms": 0.0,
            "elapsed_boundary": "Deterministic report refresh records call count; wall-clock step duration is recorded by full regression logs.",
            "reporting_boundary": "Performance smoke is secondary evidence only and does not replace correctness gates."
        }),
    )
}
