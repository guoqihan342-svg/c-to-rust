fn emit_sum_i32_buffer_performance_smoke(
    report: &SumI32BufferOracleReport,
    evidence_dir: &Path,
) -> Result<(), Box<dyn Error>> {
    let iterations = PERFORMANCE_SMOKE_ITERATIONS;
    let mut calls = 0_u64;
    for _ in 0..iterations {
        for case in &report.cases {
            let _ = sum_i32_buffer::sum_i32_buffer(&case.values);
            calls += 1;
        }
    }
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-performance-smoke.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": "demo-sum-i32-buffer-20260625",
            "status": "recorded",
            "secondary_only": true,
            "operation": "safe Rust sum_i32_buffer replay over fixture corpus",
            "iterations": iterations,
            "calls": calls,
            "elapsed_ms": 0.0,
            "elapsed_boundary": "Deterministic report refresh records call count; wall-clock step duration is recorded by full regression logs.",
            "reporting_boundary": "Performance smoke is secondary evidence only and does not replace correctness gates."
        }),
    )
}

fn emit_call_expression_chain_performance_smoke(
    report: &CallExpressionChainOracleReport,
    evidence_dir: &Path,
) -> Result<(), Box<dyn Error>> {
    let iterations = PERFORMANCE_SMOKE_ITERATIONS;
    let mut calls = 0_u64;
    for _ in 0..iterations {
        for case in &report.cases {
            let _ = call_expression_chain::call_expression_chain(case.input_value);
            calls += 1;
        }
    }
    write_json(
        &evidence_dir.join("l3-call-expression-performance-smoke.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": "demo-call-expression-20260625",
            "status": "recorded",
            "secondary_only": true,
            "operation": "safe Rust call_expression_chain replay over fixture corpus",
            "iterations": iterations,
            "calls": calls,
            "elapsed_ms": 0.0,
            "elapsed_boundary": "Deterministic report refresh records call count; wall-clock step duration is recorded by full regression logs.",
            "reporting_boundary": "Performance smoke is secondary evidence only and does not replace correctness gates."
        }),
    )
}

fn emit_signed_rshift_contract_performance_smoke(
    report: &SignedRshiftContractOracleReport,
    evidence_dir: &Path,
) -> Result<(), Box<dyn Error>> {
    let iterations = PERFORMANCE_SMOKE_ITERATIONS;
    let mut calls = 0_u64;
    for _ in 0..iterations {
        for case in &report.cases {
            let _ = signed_rshift_contract::signed_rshift_contract(case.value, case.count);
            calls += 1;
        }
    }
    write_json(
        &evidence_dir.join("l3-signed-rshift-contract-performance-smoke.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "signed-rshift-contract",
            "source_commit": "demo-signed-rshift-contract-20260628",
            "status": "recorded",
            "secondary_only": true,
            "operation": "safe Rust signed_rshift_contract replay over fixture corpus",
            "iterations": iterations,
            "calls": calls,
            "elapsed_ms": 0.0,
            "elapsed_boundary": "Deterministic report refresh records call count; wall-clock step duration is recorded by full regression logs.",
            "reporting_boundary": "Performance smoke is secondary evidence only and does not replace correctness gates."
        }),
    )
}

fn emit_external_direct_callee_performance_smoke(
    report: &ExternalDirectCalleeOracleReport,
    evidence_dir: &Path,
) -> Result<(), Box<dyn Error>> {
    let iterations = PERFORMANCE_SMOKE_ITERATIONS;
    let mut calls = 0_u64;
    for _ in 0..iterations {
        for case in &report.cases {
            let _ = external_direct_callee::call_helper_chain(case.input_value);
            calls += 1;
        }
    }
    write_json(
        &evidence_dir.join("l3-external-direct-callee-performance-smoke.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "external-direct-callee",
            "source_commit": "demo-external-direct-callee-20260625",
            "status": "recorded",
            "secondary_only": true,
            "operation": "safe Rust call_helper_chain replay over fixture corpus",
            "iterations": iterations,
            "calls": calls,
            "elapsed_ms": 0.0,
            "elapsed_boundary": "Deterministic report refresh records call count; wall-clock step duration is recorded by full regression logs.",
            "reporting_boundary": "Performance smoke is secondary evidence only and does not replace correctness gates."
        }),
    )
}

fn emit_sum_i32_ptr_arith_performance_smoke(
    report: &SumI32PtrArithOracleReport,
    evidence_dir: &Path,
) -> Result<(), Box<dyn Error>> {
    let iterations = PERFORMANCE_SMOKE_ITERATIONS;
    let mut calls = 0_u64;
    for _ in 0..iterations {
        for case in &report.cases {
            let _ = sum_i32_ptr_arith::sum_i32_ptr_arith(&case.values);
            calls += 1;
        }
    }
    write_json(
        &evidence_dir.join("l3-sum-i32-ptr-arith-performance-smoke.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": "demo-sum-i32-ptr-arith-20260625",
            "status": "recorded",
            "secondary_only": true,
            "operation": "safe Rust sum_i32_ptr_arith replay over fixture corpus",
            "iterations": iterations,
            "calls": calls,
            "elapsed_ms": 0.0,
            "elapsed_boundary": "Deterministic report refresh records call count; wall-clock step duration is recorded by full regression logs.",
            "reporting_boundary": "Performance smoke is secondary evidence only and does not replace correctness gates."
        }),
    )
}

fn emit_copy_i32_ptr_arith_performance_smoke(
    report: &CopyI32PtrArithOracleReport,
    evidence_dir: &Path,
) -> Result<(), Box<dyn Error>> {
    let iterations = PERFORMANCE_SMOKE_ITERATIONS;
    let mut calls = 0_u64;
    for _ in 0..iterations {
        for case in &report.cases {
            let _ = copy_i32_ptr_arith::copy_i32_ptr_arith(&case.values);
            calls += 1;
        }
    }
    write_json(
        &evidence_dir.join("l3-copy-i32-ptr-arith-performance-smoke.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "copy-i32-ptr-arith",
            "source_commit": "demo-copy-i32-ptr-arith-20260625",
            "status": "recorded",
            "secondary_only": true,
            "operation": "safe Rust copy_i32_ptr_arith replay over fixture corpus",
            "iterations": iterations,
            "calls": calls,
            "elapsed_ms": 0.0,
            "elapsed_boundary": "Deterministic report refresh records call count; wall-clock step duration is recorded by full regression logs.",
            "reporting_boundary": "Performance smoke is secondary evidence only and does not replace correctness gates."
        }),
    )
}
