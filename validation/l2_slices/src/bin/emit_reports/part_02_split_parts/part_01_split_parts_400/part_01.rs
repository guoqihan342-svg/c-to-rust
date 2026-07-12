fn write_libuv_negative_diff(
    report: &LibuvIp4OracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .iter()
        .find(|case| case.return_code == 0)
        .ok_or("libuv oracle must include a passing case")?;
    let rust = libuv_ip4_addr::uv_ip4_addr(&case.ip, case.port);
    let mutated_addr = if case.addr_bytes_hex == "7f000001" {
        "7f000002"
    } else {
        "7f000001"
    };
    let detected = mutated_addr != rust.addr_bytes_hex;
    write_json(
        &evidence_dir.join("l3-ip4-addr-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "first passing oracle case addr_bytes_hex is changed",
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "addr_bytes_hex",
                    "mutated_c_value": mutated_addr,
                    "rust_value": rust.addr_bytes_hex
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}

fn emit_store_add_one_negative_diff(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("store-add-one-c-oracle.json");
    let report: StoreAddOneOracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    let detected = write_store_add_one_negative_diff(&report, &evidence_dir)?;

    Ok(NegativeDiffResult {
        slice_id: "demo-store-add-one",
        status: if detected { "passed" } else { "failed" },
        report_path: "validation/evidence/demo/l3-store-add-one-negative-diff.json",
    })
}

fn write_store_add_one_negative_diff(
    report: &StoreAddOneOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .first()
        .ok_or("store_add_one oracle must include at least one case")?;
    let rust = store_add_one::store_add_one(case.value);
    let mutated_out0 = case.out0.wrapping_add(1);
    let detected = mutated_out0 != rust.out0;
    write_json(
        &evidence_dir.join("l3-store-add-one-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "source_commit": "demo-store-add-one-20260625",
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "first oracle case out0 is changed by +1",
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "out0",
                    "mutated_c_value": mutated_out0,
                    "rust_value": rust.out0
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}

fn emit_sum_i32_buffer_negative_diff(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("sum-i32-buffer-c-oracle.json");
    let report: SumI32BufferOracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    let detected = write_sum_i32_buffer_negative_diff(&report, &evidence_dir)?;

    Ok(NegativeDiffResult {
        slice_id: "demo-sum-i32-buffer",
        status: if detected { "passed" } else { "failed" },
        report_path: "validation/evidence/demo/l3-sum-i32-buffer-negative-diff.json",
    })
}

fn write_sum_i32_buffer_negative_diff(
    report: &SumI32BufferOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .iter()
        .find(|case| !case.values.is_empty())
        .ok_or("sum_i32_buffer oracle must include at least one non-empty case")?;
    let rust = sum_i32_buffer::sum_i32_buffer(&case.values);
    let mutated_sum = case.sum.wrapping_add(1);
    let detected = mutated_sum != rust.sum;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": "demo-sum-i32-buffer-20260625",
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

fn emit_call_expression_chain_negative_diff(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("call-expression-c-oracle.json");
    let report: CallExpressionChainOracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    let detected = write_call_expression_chain_negative_diff(&report, &evidence_dir)?;

    Ok(NegativeDiffResult {
        slice_id: "demo-call-expression",
        status: if detected { "passed" } else { "failed" },
        report_path: "validation/evidence/demo/l3-call-expression-negative-diff.json",
    })
}
