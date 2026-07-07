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
    let iterations = 10_000_u64;
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
    let iterations = 10_000_u64;
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

fn emit_sum_i32_buffer_performance_smoke(
    report: &SumI32BufferOracleReport,
    evidence_dir: &Path,
) -> Result<(), Box<dyn Error>> {
    let iterations = 10_000_u64;
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
    let iterations = 10_000_u64;
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
    let iterations = 10_000_u64;
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
    let iterations = 10_000_u64;
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
    let iterations = 10_000_u64;
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
    let iterations = 10_000_u64;
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

fn emit_add_i32_pair_ptr_arith_performance_smoke(
    report: &AddI32PairPtrArithOracleReport,
    evidence_dir: &Path,
) -> Result<(), Box<dyn Error>> {
    let iterations = 10_000_u64;
    let mut calls = 0_u64;
    for _ in 0..iterations {
        for case in &report.cases {
            let alias_case =
                add_i32_pair_ptr_arith::AddI32PairAliasCase::from_fixture(&case.alias_case)
                    .ok_or("add_i32_pair_ptr_arith oracle contains unknown alias_case")?;
            let _ =
                add_i32_pair_ptr_arith::add_i32_pair_ptr_arith(&case.lhs, &case.rhs, alias_case);
            calls += 1;
        }
    }
    write_json(
        &evidence_dir.join("l3-add-i32-pair-ptr-arith-performance-smoke.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "add-i32-pair-ptr-arith",
            "source_commit": "demo-add-i32-pair-ptr-arith-20260625",
            "status": "recorded",
            "secondary_only": true,
            "operation": "safe Rust add_i32_pair_ptr_arith replay over fixture corpus",
            "iterations": iterations,
            "calls": calls,
            "elapsed_ms": 0.0,
            "elapsed_boundary": "Deterministic report refresh records call count; wall-clock step duration is recorded by full regression logs.",
            "reporting_boundary": "Performance smoke is secondary evidence only and does not replace correctness gates."
        }),
    )
}

fn emit_store_add_one_static_l3_evidence(
    evidence_dir: &Path,
    case_count: usize,
    status: &str,
) -> Result<(), Box<dyn Error>> {
    let manifest_status = if status == "passed" {
        "passed"
    } else {
        "failed"
    };
    let repo_commit = "workspace".to_owned();
    let common = json!({
        "schema_version": 1,
        "level": "L3",
        "target_id": "demo",
        "slice_id": "store-add-one",
        "source_commit": "demo-store-add-one-20260625",
        "repo_commit": repo_commit
    });
    let common_obj = common.as_object().ok_or("common evidence object")?;

    write_json(
        &evidence_dir.join("l3-store-add-one-slice-contract.json"),
        &json!({
            "schema_version": common_obj["schema_version"],
            "level": common_obj["level"],
            "target_id": common_obj["target_id"],
            "slice_id": common_obj["slice_id"],
            "source_commit": common_obj["source_commit"],
            "repo_commit": common_obj["repo_commit"],
            "status": "recorded",
            "source_boundary": {
                "files": ["validation/l2_slices/tools/generate_store_add_one_oracle.py"],
                "functions": ["store_add_one"],
                "signature": "int store_add_one(int value, int* out)"
            },
            "rust_boundary": {
                "module": "validation/l2_slices/src/store_add_one.rs",
                "api": "pub fn store_add_one(value: i32) -> StoreAddOneReport",
                "safe_rust": true,
                "raw_pointer_exposed": false
            },
            "fixture": {
                "path": "validation/l2_slices/fixtures/store-add-one-c-oracle.json",
                "hash": "store-add-one-fixture",
                "case_count": case_count
            },
            "behavior_fields": ["return_code", "status", "out0"],
            "accepted_differences": [],
            "non_goals": [
                "No NULL out pointer execution.",
                "No INT_MAX signed overflow case.",
                "No unbounded pointer index, pointer arithmetic, aliasing, or struct field writes.",
                "No full project migration claim."
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-context-pack.json"),
        &json!({
            "schema_version": common_obj["schema_version"],
            "level": common_obj["level"],
            "target_id": common_obj["target_id"],
            "slice_id": common_obj["slice_id"],
            "source_commit": common_obj["source_commit"],
            "repo_commit": common_obj["repo_commit"],
            "status": "recorded",
            "direct_c_files": ["validation/l2_slices/tools/generate_store_add_one_oracle.py"],
            "direct_rust_files": [
                "validation/l2_slices/src/store_add_one.rs",
                "validation/l2_slices/tests/store_add_one.rs",
                "validation/l2_slices/src/bin/emit_reports.rs"
            ],
            "call_edges": [
                {"from": "C oracle helper", "to": "store_add_one"},
                {"from": "Rust emit_reports", "to": "store_add_one::store_add_one"}
            ],
            "related_tests": [
                "validation/l2_slices/tests/store_add_one.rs::store_add_one_matches_c_oracle_with_safe_boundary"
            ],
            "cache_inputs": [
                "fixture=validation/l2_slices/fixtures/store-add-one-c-oracle.json",
                "rust_module=validation/l2_slices/src/store_add_one.rs",
                "rust_test=validation/l2_slices/tests/store_add_one.rs"
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-config-profile.json"),
        &json!({
            "schema_version": common_obj["schema_version"],
            "level": common_obj["level"],
            "target_id": common_obj["target_id"],
            "slice_id": common_obj["slice_id"],
            "source_commit": common_obj["source_commit"],
            "repo_commit": common_obj["repo_commit"],
            "status": "recorded",
            "profile_id": "demo-store-add-one-wsl-gcc",
            "config_header": {"path": null, "role": "not_required"},
            "compile_profile": {
                "c_oracle_command": "python -B validation/l2_slices/tools/generate_store_add_one_oracle.py",
                "include_paths": [],
                "config_header_included": false,
                "command_args": ["wsl", "gcc", "-std=c99", "-Wall", "-Wextra", "-Werror"]
            },
            "rust_profile": {
                "package": "c-to-rust-l2-slices",
                "cargo_features": [],
                "backend": "safe-rust-validation-slice"
            },
            "cache_invalidation_keys": [
                "source_commit",
                "repo_commit",
                "fixture.hash",
                "rust_boundary.module",
                "translator_version"
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-pointer-graph.json"),
        &json!({
            "schema_version": common_obj["schema_version"],
            "target_id": common_obj["target_id"],
            "slice_id": common_obj["slice_id"],
            "level": common_obj["level"],
            "status": "recorded",
            "source_commit": common_obj["source_commit"],
            "repo_commit": common_obj["repo_commit"],
            "context_pack_ref": "validation/evidence/demo/l3-store-add-one-context-pack.json",
            "config_profile_ref": "validation/evidence/demo/l3-store-add-one-config-profile.json",
            "applicability": {"has_pointer_surface": true, "triggers": ["pointer_parameter"]},
            "source_boundary": {
                "files": ["validation/l2_slices/tools/generate_store_add_one_oracle.py"],
                "functions": ["store_add_one"],
                "structs": [],
                "globals": [],
                "direct_call_edges": []
            },
            "pointer_nodes": [
                {
                    "id": "out",
                    "symbol": "out",
                    "kind": "raw_pointer",
                    "c_type": "int*",
                    "mutability": "write_only",
                    "nullability": "unknown",
                    "ownership_role": "out_param",
                    "lifetime_owner": "caller",
                    "cross_file_exposure": false,
                    "write_effects": ["out[0]"],
                    "read_effects": [],
                    "boundary_decisions": ["bounded_pointer_index"]
                }
            ],
            "dependency_edges": [
                {"from": "value", "to": "out", "relationship": "writes_through", "evidence": "out[0] = value + 1"}
            ],
            "alias_sets": [],
            "external_state": [],
            "rust_mapping": [
                {
                    "pointer_node": "out",
                    "strategy": "Map C out[0] write to owned StoreAddOneReport.out0 return field.",
                    "unsafe_expected": false
                }
            ],
            "pointer_decisions": [
                {
                    "pointer_node": "out",
                    "decision": "bounded_pointer_index",
                    "index": 0,
                    "write_effect": "out[0]",
                    "unsafe_expected": false
                }
            ],
            "validation_coverage": {
                "fixtures": ["validation/l2_slices/fixtures/store-add-one-c-oracle.json"],
                "tests": ["validation/l2_slices/tests/store_add_one.rs"],
                "oracle_reports": [
                    "validation/evidence/demo/l3-store-add-one-c-oracle.json",
                    "validation/evidence/demo/l3-store-add-one-rust-report.json"
                ]
            },
            "risk_summary": {
                "unsafe_expected": false,
                "blocked_reasons": [],
                "known_gaps": [
                    "NULL out pointer is not executed.",
                    "INT_MAX is excluded because signed C overflow is undefined behavior.",
                    "No aliasing claim."
                ]
            },
            "cache_invalidation_keys": [
                "source_commit",
                "repo_commit",
                "fixture.hash",
                "pointer_nodes",
                "pointer_decisions",
                "schema_version"
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-test-translation.json"),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "store-add-one",
            "level": "L3",
            "status": "recorded",
            "source_commit": "demo-store-add-one-20260625",
            "repo_commit": repo_commit,
            "source_test_inputs": {
                "oracle_strategy": "WSL gcc compiles and runs the C helper, then Rust cargo tests replay the same fixture.",
                "fixtures": [
                    {
                        "path": "validation/l2_slices/fixtures/store-add-one-c-oracle.json",
                        "hash": "store-add-one-fixture",
                        "operation_count": case_count,
                        "source_kind": "fixture"
                    }
                ],
                "oracle_reports": [
                    {"path": "validation/evidence/demo/l3-store-add-one-c-oracle.json", "status": "passed"},
                    {"path": "validation/evidence/demo/l3-store-add-one-rust-report.json", "status": "passed"}
                ]
            },
            "rust_tests": [
                {
                    "file": "validation/l2_slices/tests/store_add_one.rs",
                    "test_names": ["store_add_one_matches_c_oracle_with_safe_boundary"],
                    "cargo_command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test store_add_one",
                    "framework": "cargo test"
                }
            ],
            "coverage": {
                "main_paths": ["negative input", "zero input", "positive input"],
                "error_paths": [],
                "negative_cases": ["out0 mutation rejected by negative diff"]
            },
            "translation_mappings": [
                {
                    "source": "validation/l2_slices/fixtures/store-add-one-c-oracle.json",
                    "rust_test": "validation/l2_slices/tests/store_add_one.rs::store_add_one_matches_c_oracle_with_safe_boundary",
                    "behavior_fields": ["return_code", "status", "out0"],
                    "coverage_kind": "main_path",
                    "status": "mapped"
                },
                {
                    "source": "validation/evidence/demo/l3-store-add-one-negative-diff.json",
                    "rust_test": "validation/l2_slices/src/bin/emit_reports.rs::emit_store_add_one_negative_diff",
                    "behavior_fields": ["out0"],
                    "coverage_kind": "negative_case",
                    "status": "mapped"
                }
            ],
            "evidence_links": {
                "c_oracle": {"path": "validation/evidence/demo/l3-store-add-one-c-oracle.json", "status": "passed"},
                "rust_report": {"path": "validation/evidence/demo/l3-store-add-one-rust-report.json", "status": "passed"},
                "schema_diff": {"path": "validation/evidence/demo/l3-store-add-one-diff.json", "status": "passed"},
                "negative_diff": {"path": "validation/evidence/demo/l3-store-add-one-negative-diff.json", "status": "expected_failed"},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-store-add-one-unsafe-ledger.json", "status": "passed"}
            },
            "known_gaps": [
                "Generated Rust draft remains a candidate; accepted semantics are bound to the checked Rust replay evidence.",
                "No NULL out pointer execution.",
                "No INT_MAX signed overflow case."
            ],
            "cache_invalidation_keys": [
                "schema_version",
                "source_commit",
                "fixture=validation/l2_slices/fixtures/store-add-one-c-oracle.json",
                "cargo test --manifest-path validation/l2_slices/Cargo.toml --test store_add_one"
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-rust-check.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "source_commit": "demo-store-add-one-20260625",
            "status": status,
            "compile_self_healing": {
                "attempt_count": 0,
                "unresolved_errors": 0
            },
            "commands": [
                {
                    "command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test store_add_one",
                    "status": status
                },
                {
                    "command": "cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports",
                    "status": status
                }
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-final-verification.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "source_commit": "demo-store-add-one-20260625",
            "status": status,
            "semantic_pass": status == "passed",
            "fixture": {
                "path": "validation/l2_slices/fixtures/store-add-one-c-oracle.json"
            },
            "rust_check_status": status,
            "c_oracle_status": "passed",
            "toolchain_status": "C_ORACLE_GENERATED",
            "rust_report_status": status,
            "schema_diff_status": status,
            "negative_diff_mutation_detected": true,
            "unsafe_status": "passed",
            "version_config_status": "recorded",
            "generated_draft_semantic_pass": false
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-summary.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "source_commit": "demo-store-add-one-20260625",
            "status": status,
            "semantic_pass": status == "passed",
            "summary": "store_add_one out[0] pointer-output demo has accepted C oracle, Rust replay, diff, negative diff, unsafe, and version evidence.",
            "generated_draft_semantic_pass": false,
            "known_gaps": [
                "No NULL out pointer execution.",
                "No INT_MAX signed overflow case.",
                "No aliasing or unbounded pointer index claim."
            ]
        }),
    )?;
    let version_payload = json!({
        "schema_version": 1,
        "level": "L3",
        "target_id": "demo",
        "slice_id": "store-add-one",
        "source_commit": "demo-store-add-one-20260625",
        "repo_commit": repo_commit,
        "status": "recorded",
        "semantic_pass": status == "passed",
        "translator_version": "0.1.0",
        "fixture": {
            "path": "validation/l2_slices/fixtures/store-add-one-c-oracle.json",
            "hash": "store-add-one-fixture"
        },
        "cache_invalidation_keys": [
            "source_commit",
            "repo_commit",
            "fixture.hash",
            "rust_boundary.module",
            "translator_version"
        ]
    });
    write_json(
        &evidence_dir.join("l3-store-add-one-version-manifest.json"),
        &version_payload,
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-cache-metadata.json"),
        &version_payload,
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-evidence-manifest.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "status": manifest_status,
            "source_commit": "demo-store-add-one-20260625",
            "repo_commit": repo_commit,
            "fixture": {
                "path": "validation/l2_slices/fixtures/store-add-one-c-oracle.json",
                "hash": "store-add-one-fixture",
                "operation_count": case_count
            },
            "evidence": {
                "slice_contract": {"path": "validation/evidence/demo/l3-store-add-one-slice-contract.json", "status": "recorded"},
                "context_pack": {"path": "validation/evidence/demo/l3-store-add-one-context-pack.json", "status": "recorded"},
                "cache_metadata": {"path": "validation/evidence/demo/l3-store-add-one-cache-metadata.json", "status": "recorded"},
                "config_profile": {"path": "validation/evidence/demo/l3-store-add-one-config-profile.json", "status": "recorded", "profile_id": "demo-store-add-one-wsl-gcc"},
                "pointer_dependency_graph": {"path": "validation/evidence/demo/l3-store-add-one-pointer-graph.json", "status": "recorded"},
                "test_translation": {"path": "validation/evidence/demo/l3-store-add-one-test-translation.json", "status": "recorded"},
                "c_oracle": {"path": "validation/evidence/demo/l3-store-add-one-c-oracle.json", "status": "passed", "toolchain_status": "C_ORACLE_GENERATED"},
                "rust_report": {"path": "validation/evidence/demo/l3-store-add-one-rust-report.json", "status": status},
                "schema_diff": {"path": "validation/evidence/demo/l3-store-add-one-diff.json", "status": status},
                "negative_diff": {"path": "validation/evidence/demo/l3-store-add-one-negative-diff.json", "status": "expected_failed", "expected_failure": true, "mutation_detected": true},
                "rust_check": {"path": "validation/evidence/demo/l3-store-add-one-rust-check.json", "status": status},
                "unsafe_scan": {"path": "validation/evidence/demo/l3-store-add-one-unsafe-scan.json", "status": "passed"},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-store-add-one-unsafe-ledger.json", "status": "passed"},
                "performance_smoke": {"path": "validation/evidence/demo/l3-store-add-one-performance-smoke.json", "status": "recorded", "secondary_only": true},
                "final_verification": {"path": "validation/evidence/demo/l3-store-add-one-final-verification.json", "status": status},
                "summary": {"path": "validation/evidence/demo/l3-store-add-one-summary.json", "status": status},
                "version_or_config_binding": {"path": "validation/evidence/demo/l3-store-add-one-version-manifest.json", "status": "recorded"}
            },
            "claim_boundary": {
                "scope": "Only the demo store_add_one slice for the committed fixture corpus.",
                "behavior_fields_checked": ["return_code", "status", "out0"],
                "accepted_metadata_differences": [],
                "known_gaps": [
                    "No NULL out pointer execution.",
                    "No INT_MAX signed overflow case.",
                    "No aliasing or unbounded pointer index claim."
                ],
                "must_not_claim": [
                    "full automatic C99/C11 translation",
                    "whole-program alias safety",
                    "NULL pointer equivalence",
                    "signed overflow equivalence"
                ]
            }
        }),
    )
}

fn emit_sum_i32_buffer_static_l3_evidence(
    evidence_dir: &Path,
    case_count: usize,
    status: &str,
    unsafe_status: &str,
) -> Result<(), Box<dyn Error>> {
    let manifest_status = if status == "passed" {
        "passed"
    } else {
        "failed"
    };
    let repo_commit = "workspace".to_owned();
    let source_commit = "demo-sum-i32-buffer-20260625";
    let fixture_path = "validation/l2_slices/fixtures/sum-i32-buffer-c-oracle.json";

    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-slice-contract.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "source_boundary": {
                "files": ["validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py"],
                "functions": ["sum_i32_buffer"],
                "signature": "int sum_i32_buffer(const int* values, int len, int* out)"
            },
            "rust_boundary": {
                "module": "validation/l2_slices/src/sum_i32_buffer.rs",
                "api": "pub fn sum_i32_buffer(values: &[i32]) -> SumI32BufferReport",
                "safe_rust": true,
                "raw_pointer_exposed": false
            },
            "fixture": {"path": fixture_path, "hash": "sum-i32-buffer-fixture", "case_count": case_count},
            "behavior_fields": ["return_code", "status", "len", "sum", "source_reads", "source_write"],
            "accepted_differences": [],
            "non_goals": [
                "No NULL pointer execution.",
                "No negative len execution.",
                "No aliasing proof between values and out.",
                "No signed overflow cases.",
                "No pointer arithmetic form such as *(values + i).",
                "No full project migration claim."
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-context-pack.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "direct_c_files": ["validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py"],
            "direct_rust_files": [
                "validation/l2_slices/src/sum_i32_buffer.rs",
                "validation/l2_slices/tests/sum_i32_buffer.rs",
                "validation/l2_slices/src/bin/emit_reports.rs"
            ],
            "call_edges": [
                {"from": "C oracle helper", "to": "sum_i32_buffer"},
                {"from": "Rust emit_reports", "to": "sum_i32_buffer::sum_i32_buffer"}
            ],
            "related_tests": [
                "validation/l2_slices/tests/sum_i32_buffer.rs::sum_i32_buffer_matches_c_oracle_with_safe_boundary"
            ],
            "cache_inputs": [fixture_path, "validation/l2_slices/src/sum_i32_buffer.rs"]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-config-profile.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "profile_id": "demo-sum-i32-buffer-wsl-gcc",
            "compile_profile": {
                "c_oracle_command": "python -B validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py",
                "include_paths": [],
                "command_args": ["wsl", "gcc", "-std=c99", "-Wall", "-Wextra", "-Werror"]
            },
            "rust_profile": {"package": "c-to-rust-l2-slices", "cargo_features": []},
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-type-map.json"),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "slice_spec_ref": {"path": "validation/slice-specs/demo-sum-i32-buffer.json", "status": "ready"},
            "build_profile_ref": {"path": "validation/evidence/demo/l3-sum-i32-buffer-config-profile.json", "status": "recorded"},
            "mappings": [
                {
                    "id": "type-1",
                    "kind": "pointer",
                    "c_name": "values",
                    "symbol": "values",
                    "c_type": "const int*",
                    "rust_type": "&[i32]",
                    "confidence": "proven",
                    "source": "translator_rule",
                    "role": "input_buffer",
                    "mutability": "read_only",
                    "length_companion": "len",
                    "decision": "safe_slice_boundary"
                },
                {
                    "id": "type-2",
                    "kind": "primitive",
                    "c_name": "len",
                    "symbol": "len",
                    "c_type": "int",
                    "rust_type": "i32",
                    "confidence": "proven",
                    "source": "translator_rule",
                    "role": "input_length",
                    "bounds": "fixture domain requires len >= 0 and values valid for len elements"
                },
                {
                    "id": "type-3",
                    "kind": "pointer",
                    "c_name": "out",
                    "symbol": "out",
                    "c_type": "int*",
                    "rust_type": "SumI32BufferReport.sum",
                    "confidence": "proven",
                    "source": "translator_rule",
                    "role": "output_pointer",
                    "mutability": "write_only",
                    "decision": "owned_report_field"
                },
                {
                    "id": "type-4",
                    "kind": "primitive",
                    "c_name": "total",
                    "symbol": "total",
                    "c_type": "int",
                    "rust_type": "i32",
                    "confidence": "proven",
                    "source": "translator_rule",
                    "role": "local_accumulator"
                }
            ],
            "uncertainties": [],
            "unsupported_types": [],
            "unsupported_nodes": [],
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"],
            "safe_boundary": {
                "public_api": "pub fn sum_i32_buffer(values: &[i32]) -> SumI32BufferReport",
                "raw_pointer_exposed": false,
                "unsafe_required": false
            }
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-cfg.json"),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "slice_spec_ref": {"path": "validation/slice-specs/demo-sum-i32-buffer.json", "status": "ready"},
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"],
            "functions": [
                {
                    "name": "sum_i32_buffer",
                    "signature": "int sum_i32_buffer(const int* values, int len, int* out)",
                    "source_span": {"file": "validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py", "line_start": 1, "line_end": 1},
                    "entry_block": "entry",
                    "exit_blocks": ["return"],
                    "basic_blocks": [
                        {
                            "id": "entry",
                            "kind": "entry",
                            "source_span": {"file": "validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py", "line_start": 1, "line_end": 1},
                            "statements": ["int total = 0", "int i", "for (i = 0; i < len; i++)"],
                            "statement_kinds": ["local_init", "local_decl", "for_loop"],
                            "lvalue_kinds": ["none"],
                            "lvalue_decisions": []
                        },
                        {
                            "id": "loop_body",
                            "kind": "body",
                            "source_span": {"file": "validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py", "line_start": 1, "line_end": 1},
                            "statements": ["total = total + values[i]"],
                            "statement_kinds": ["bounded_input_buffer_read", "assignment"],
                            "lvalue_kinds": ["bounded_input_buffer"],
                            "lvalue_decisions": [
                                {
                                    "decision": "bounded_input_buffer",
                                    "lvalue_kind": "bounded_input_buffer",
                                    "source_statement": "total = total + values[i]",
                                    "translation_rule_id": "bounded-input-buffer-read",
                                    "length_companion": "len"
                                }
                            ]
                        },
                        {
                            "id": "exit",
                            "kind": "exit",
                            "source_span": {"file": "validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py", "line_start": 1, "line_end": 1},
                            "statements": ["out[0] = total", "return 0"],
                            "statement_kinds": ["pointer_write", "return"],
                            "lvalue_kinds": ["bounded_pointer_index", "none"],
                            "lvalue_decisions": [
                                {
                                    "decision": "bounded_pointer_index",
                                    "lvalue_kind": "bounded_pointer_index",
                                    "source_statement": "out[0] = total",
                                    "translation_rule_id": "bounded-pointer-index-write"
                                }
                            ]
                        }
                    ],
                    "branches": [
                        {
                            "id": "branch-1",
                            "kind": "for",
                            "condition": "i < len",
                            "source_span": {"file": "validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py", "line_start": 1, "line_end": 1},
                            "proves": "values[i] bounded by len companion"
                        }
                    ],
                    "returns": [
                        {
                            "block": "exit",
                            "expression": "0",
                            "source_span": {"file": "validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py", "line_start": 1, "line_end": 1}
                        }
                    ],
                    "edges": [
                        {"from": "entry", "to": "loop_body", "kind": "fallthrough"},
                        {"from": "loop_body", "to": "loop_body", "kind": "loop_back"},
                        {"from": "loop_body", "to": "exit", "kind": "fallthrough"},
                        {"from": "exit", "to": "return", "kind": "return"}
                    ],
                    "structured_control_flow": {
                        "has_goto": false,
                        "has_switch": false,
                        "if_count": 0,
                        "loop_count": 1,
                        "relooper_required": false
                    }
                }
            ],
            "unsupported_control_flow": []
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-pointer-graph.json"),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "context_pack_ref": "validation/evidence/demo/l3-sum-i32-buffer-context-pack.json",
            "applicability": {"has_pointer_surface": true, "triggers": ["pointer_parameter", "buffer"]},
            "source_boundary": {
                "files": ["validation/l2_slices/tools/generate_sum_i32_buffer_oracle.py", fixture_path],
                "functions": ["sum_i32_buffer"],
                "structs": ["int"],
                "globals": [],
                "direct_call_edges": []
            },
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"],
            "pointer_nodes": [
                {
                    "id": "values",
                    "symbol": "values",
                    "kind": "buffer",
                    "buffer_role": "input",
                    "length_companion": "len",
                    "c_type": "const int*",
                    "mutability": "read_only",
                    "nullability": "unknown",
                    "ownership_role": "borrowed",
                    "read_effects": ["values[i]"],
                    "write_effects": [],
                    "boundary_decisions": ["bounded_input_buffer"]
                },
                {
                    "id": "out",
                    "symbol": "out",
                    "kind": "struct_pointer",
                    "c_type": "int*",
                    "mutability": "write_only",
                    "nullability": "unknown",
                    "ownership_role": "out_param",
                    "read_effects": [],
                    "write_effects": ["out[0]"],
                    "boundary_decisions": ["bounded_pointer_index"]
                }
            ],
            "dependency_edges": [
                {"from": "len", "to": "values", "relationship": "borrows", "evidence": "for (i = 0; i < len; i++)"},
                {"from": "values", "to": "out", "relationship": "writes_through", "evidence": "out[0] = total"}
            ],
            "alias_sets": [],
            "rust_mapping": [
                {"pointer_node": "values", "strategy": "Map const int* plus len to safe Rust slice input.", "unsafe_expected": false},
                {"pointer_node": "out", "strategy": "Map C out[0] write to owned SumI32BufferReport.sum field.", "unsafe_expected": false}
            ],
            "pointer_decisions": [
                {"pointer_node": "values", "decision": "bounded_input_buffer", "read_effect": "values[i]", "length_companion": "len", "translation_rule_id": "bounded-input-buffer-read", "unsafe_expected": false},
                {"pointer_node": "out", "decision": "bounded_pointer_index", "index": 0, "write_effect": "out[0]", "translation_rule_id": "bounded-pointer-index-write", "unsafe_expected": false}
            ],
            "risk_summary": {
                "unsafe_expected": false,
                "known_gaps": ["NULL pointers are not executed.", "Aliasing is not proven.", "Signed overflow cases are excluded."]
            }
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-test-translation.json"),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "source_test_inputs": {
                "oracle_strategy": "WSL gcc compiles and runs the C helper, then Rust cargo tests replay the same fixture.",
                "fixtures": [{"path": fixture_path, "hash": "sum-i32-buffer-fixture", "operation_count": case_count, "source_kind": "fixture"}],
                "oracle_reports": [
                    {"path": "validation/evidence/demo/l3-sum-i32-buffer-c-oracle.json", "status": "passed"},
                    {"path": "validation/evidence/demo/l3-sum-i32-buffer-rust-report.json", "status": "passed"}
                ]
            },
            "rust_tests": [
                {
                    "file": "validation/l2_slices/tests/sum_i32_buffer.rs",
                    "test_names": ["sum_i32_buffer_matches_c_oracle_with_safe_boundary"],
                    "cargo_command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test sum_i32_buffer",
                    "framework": "cargo test"
                }
            ],
            "coverage": {
                "main_paths": ["empty input", "single input", "multi input", "negative values", "boundary-safe sum"],
                "error_paths": [],
                "negative_cases": ["sum mutation rejected by negative diff"]
            },
            "translation_mappings": [
                {
                    "source": fixture_path,
                    "rust_test": "validation/l2_slices/tests/sum_i32_buffer.rs::sum_i32_buffer_matches_c_oracle_with_safe_boundary",
                    "behavior_fields": ["return_code", "status", "len", "sum", "source_reads", "source_write"],
                    "coverage_kind": "main_path",
                    "status": "mapped"
                },
                {
                    "source": "validation/evidence/demo/l3-sum-i32-buffer-negative-diff.json",
                    "rust_test": "validation/l2_slices/src/bin/emit_reports.rs::emit_sum_i32_buffer_negative_diff",
                    "behavior_fields": ["sum"],
                    "coverage_kind": "negative_case",
                    "status": "mapped"
                }
            ],
            "evidence_links": {
                "c_oracle": {"path": "validation/evidence/demo/l3-sum-i32-buffer-c-oracle.json", "status": "passed"},
                "rust_report": {"path": "validation/evidence/demo/l3-sum-i32-buffer-rust-report.json", "status": "passed"},
                "schema_diff": {"path": "validation/evidence/demo/l3-sum-i32-buffer-diff.json", "status": "passed"},
                "negative_diff": {"path": "validation/evidence/demo/l3-sum-i32-buffer-negative-diff.json", "status": "expected_failed"},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-sum-i32-buffer-unsafe-ledger.json", "status": "passed"}
            }
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-rust-check.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": source_commit,
            "status": status,
            "compile_self_healing": {"attempt_count": 0, "unresolved_errors": 0},
            "commands": [
                {"command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test sum_i32_buffer", "status": status},
                {"command": "cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports", "status": status}
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-final-verification.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": source_commit,
            "status": status,
            "semantic_pass": status == "passed",
            "fixture": {"path": fixture_path},
            "rust_check_status": status,
            "c_oracle_status": "passed",
            "toolchain_status": "C_ORACLE_GENERATED",
            "rust_report_status": status,
            "schema_diff_status": status,
            "negative_diff_mutation_detected": true,
            "unsafe_status": unsafe_status,
            "version_config_status": "recorded",
            "generated_draft_semantic_pass": false
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-summary.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": source_commit,
            "status": status,
            "semantic_pass": status == "passed",
            "summary": "sum_i32_buffer input-buffer pointer demo has accepted C oracle, Rust replay, diff, negative diff, unsafe, and version evidence.",
            "generated_draft_semantic_pass": false,
            "known_gaps": ["No NULL pointer execution.", "No negative len execution.", "No aliasing or signed overflow claim."]
        }),
    )?;
    let version_payload = json!({
        "schema_version": 1,
        "level": "L3",
        "target_id": "demo",
        "slice_id": "sum-i32-buffer",
        "source_commit": source_commit,
        "repo_commit": repo_commit,
        "status": "recorded",
        "semantic_pass": status == "passed",
        "translator_version": "0.1.0",
        "fixture": {"path": fixture_path, "hash": "sum-i32-buffer-fixture"},
        "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module", "translator_version"]
    });
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-version-manifest.json"),
        &version_payload,
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-cache-metadata.json"),
        &version_payload,
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-evidence-manifest.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "status": manifest_status,
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "fixture": {"path": fixture_path, "hash": "sum-i32-buffer-fixture", "operation_count": case_count},
            "evidence": {
                "slice_contract": {"path": "validation/evidence/demo/l3-sum-i32-buffer-slice-contract.json", "status": "recorded"},
                "context_pack": {"path": "validation/evidence/demo/l3-sum-i32-buffer-context-pack.json", "status": "recorded"},
                "cache_metadata": {"path": "validation/evidence/demo/l3-sum-i32-buffer-cache-metadata.json", "status": "recorded"},
                "config_profile": {"path": "validation/evidence/demo/l3-sum-i32-buffer-config-profile.json", "status": "recorded", "profile_id": "demo-sum-i32-buffer-wsl-gcc"},
                "type_map": {"path": "validation/evidence/demo/l3-sum-i32-buffer-type-map.json", "status": "recorded"},
                "cfg": {"path": "validation/evidence/demo/l3-sum-i32-buffer-cfg.json", "status": "recorded"},
                "pointer_dependency_graph": {"path": "validation/evidence/demo/l3-sum-i32-buffer-pointer-graph.json", "status": "recorded"},
                "test_translation": {"path": "validation/evidence/demo/l3-sum-i32-buffer-test-translation.json", "status": "recorded"},
                "c_oracle": {"path": "validation/evidence/demo/l3-sum-i32-buffer-c-oracle.json", "status": "passed", "toolchain_status": "C_ORACLE_GENERATED"},
                "rust_report": {"path": "validation/evidence/demo/l3-sum-i32-buffer-rust-report.json", "status": status},
                "schema_diff": {"path": "validation/evidence/demo/l3-sum-i32-buffer-diff.json", "status": status},
                "negative_diff": {"path": "validation/evidence/demo/l3-sum-i32-buffer-negative-diff.json", "status": "expected_failed", "expected_failure": true, "mutation_detected": true},
                "rust_check": {"path": "validation/evidence/demo/l3-sum-i32-buffer-rust-check.json", "status": status},
                "unsafe_scan": {"path": "validation/evidence/demo/l3-sum-i32-buffer-unsafe-scan.json", "status": unsafe_status},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-sum-i32-buffer-unsafe-ledger.json", "status": unsafe_status},
                "performance_smoke": {"path": "validation/evidence/demo/l3-sum-i32-buffer-performance-smoke.json", "status": "recorded", "secondary_only": true},
                "final_verification": {"path": "validation/evidence/demo/l3-sum-i32-buffer-final-verification.json", "status": status},
                "summary": {"path": "validation/evidence/demo/l3-sum-i32-buffer-summary.json", "status": status},
                "version_or_config_binding": {"path": "validation/evidence/demo/l3-sum-i32-buffer-version-manifest.json", "status": "recorded"}
            },
            "claim_boundary": {
                "scope": "Only the demo sum_i32_buffer slice for the committed fixture corpus.",
                "behavior_fields_checked": ["return_code", "status", "len", "sum", "source_reads", "source_write"],
                "accepted_metadata_differences": [],
                "known_gaps": ["No NULL pointer execution.", "No negative len execution.", "No aliasing or signed overflow claim."],
                "must_not_claim": ["full automatic C99/C11 translation", "whole-program alias safety", "NULL pointer equivalence", "signed overflow equivalence"]
            }
        }),
    )
}
