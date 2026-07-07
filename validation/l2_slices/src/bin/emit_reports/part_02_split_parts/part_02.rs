fn write_call_expression_chain_negative_diff(
    report: &CallExpressionChainOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .iter()
        .find(|case| case.input_value > 0)
        .ok_or("call_expression_chain oracle must include at least one recursive case")?;
    let rust = call_expression_chain::call_expression_chain(case.input_value);
    let mutated_count = case.call_expression_count.saturating_sub(1);
    let detected = mutated_count != rust.call_expression_count
        || case.call_expression_contexts != rust.call_expression_contexts;
    write_json(
        &evidence_dir.join("l3-call-expression-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": "demo-call-expression-20260625",
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "detected": detected,
            "mutation": "recursive oracle case call_expression_count is changed by -1",
            "mutated_fields": ["call_expression_count"],
            "compared_fields": ["return_value", "status", "call_expression_count", "call_expression_contexts", "source_calls"],
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "call_expression_count",
                    "mutated_c_value": mutated_count,
                    "rust_value": rust.call_expression_count
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}

fn emit_signed_rshift_contract_negative_diff(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("signed-rshift-contract-c-oracle.json");
    let report: SignedRshiftContractOracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    let detected = write_signed_rshift_contract_negative_diff(&report, &evidence_dir)?;

    Ok(NegativeDiffResult {
        slice_id: "demo-signed-rshift-contract",
        status: if detected { "passed" } else { "failed" },
        report_path: "validation/evidence/demo/l3-signed-rshift-contract-negative-diff.json",
    })
}

fn write_signed_rshift_contract_negative_diff(
    report: &SignedRshiftContractOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .first()
        .ok_or("signed_rshift_contract oracle must include at least one case")?;
    let rust = signed_rshift_contract::signed_rshift_contract(case.value, case.count);
    let mutated_contract = "logical_right_shift";
    let detected = mutated_contract != rust.contract;
    write_json(
        &evidence_dir.join("l3-signed-rshift-contract-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "signed-rshift-contract",
            "source_commit": "demo-signed-rshift-contract-20260628",
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "first oracle case implementation-defined signed right shift contract is changed",
            "case_id": case.id,
            "compared_fields": ["return_value", "status", "contract"],
            "mutated_fields": ["contract"],
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "contract",
                    "mutated_c_value": mutated_contract,
                    "rust_value": rust.contract
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}
