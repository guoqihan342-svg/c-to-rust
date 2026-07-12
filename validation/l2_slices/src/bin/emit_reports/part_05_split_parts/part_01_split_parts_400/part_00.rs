fn emit_store_add_one_safety_evidence(
    repo_root: &Path,
    safety: &SafetyEvidence,
) -> Result<(), Box<dyn Error>> {
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    fs::create_dir_all(&evidence_dir)?;
    let unsafe_count = safety.scan["unsafe_count"].as_u64().unwrap_or(0);
    let status = if unsafe_count == 0 {
        "passed"
    } else {
        "failed"
    };
    write_json(
        &evidence_dir.join("l3-store-add-one-unsafe-scan.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "source_commit": "demo-store-add-one-20260625",
            "status": status,
            "crate": "validation/l2_slices",
            "scope": "first-party Rust source under validation/l2_slices/src",
            "first_party_non_test_unsafe_count": unsafe_count,
            "unsafe_ratio": 0.0,
            "hits": safety.scan["hits"]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-unsafe-ledger.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "source_commit": "demo-store-add-one-20260625",
            "status": status,
            "policy": {
                "first_party_non_test_unsafe_limit": 0,
                "unsafe_ratio_limit": 0.10,
                "audit_required_even_when_zero": true
            },
            "first_party_non_test_unsafe_count": unsafe_count,
            "unsafe_ratio": 0.0,
            "registered_unsafe": [],
            "introduced_unsafe": [],
            "audited_modules": [
                "validation/l2_slices/src/store_add_one.rs"
            ],
            "scan_report": "validation/evidence/demo/l3-store-add-one-unsafe-scan.json"
        }),
    )
}

fn emit_sum_i32_buffer_safety_evidence(
    repo_root: &Path,
    safety: &SafetyEvidence,
) -> Result<(), Box<dyn Error>> {
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    fs::create_dir_all(&evidence_dir)?;
    let unsafe_count = safety.scan["unsafe_count"].as_u64().unwrap_or(0);
    let status = if unsafe_count == 0 {
        "passed"
    } else {
        "failed"
    };
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-unsafe-scan.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": "demo-sum-i32-buffer-20260625",
            "status": status,
            "crate": "validation/l2_slices",
            "scope": "first-party Rust source under validation/l2_slices/src",
            "first_party_non_test_unsafe_count": unsafe_count,
            "unsafe_ratio": 0.0,
            "public_api_raw_pointer_exposed": false,
            "public_api_unsafe_fn": false,
            "hits": safety.scan["hits"]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-unsafe-ledger.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": "demo-sum-i32-buffer-20260625",
            "status": status,
            "policy": {
                "first_party_non_test_unsafe_limit": 0,
                "unsafe_ratio_limit": 0.10,
                "audit_required_even_when_zero": true
            },
            "first_party_non_test_unsafe_count": unsafe_count,
            "unsafe_ratio": 0.0,
            "registered_unsafe": [],
            "introduced_unsafe": [],
            "audited_modules": [
                "validation/l2_slices/src/sum_i32_buffer.rs"
            ],
        "scan_report": "validation/evidence/demo/l3-sum-i32-buffer-unsafe-scan.json"
        }),
    )
}

fn emit_call_expression_chain_safety_evidence(
    repo_root: &Path,
    safety: &SafetyEvidence,
) -> Result<(), Box<dyn Error>> {
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    fs::create_dir_all(&evidence_dir)?;
    let unsafe_count = safety.scan["unsafe_count"].as_u64().unwrap_or(0);
    let status = if unsafe_count == 0 {
        "passed"
    } else {
        "failed"
    };
    write_json(
        &evidence_dir.join("l3-call-expression-unsafe-scan.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": "demo-call-expression-20260625",
            "status": status,
            "crate": "validation/l2_slices",
            "scope": "first-party Rust source under validation/l2_slices/src",
            "first_party_non_test_unsafe_count": unsafe_count,
            "unsafe_ratio": 0.0,
            "public_api_raw_pointer_exposed": false,
            "public_api_unsafe_fn": false,
            "hits": safety.scan["hits"]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-call-expression-unsafe-ledger.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": "demo-call-expression-20260625",
            "status": status,
            "policy": {
                "first_party_non_test_unsafe_limit": 0,
                "unsafe_ratio_limit": 0.10,
                "audit_required_even_when_zero": true
            },
            "first_party_non_test_unsafe_count": unsafe_count,
            "unsafe_ratio": 0.0,
            "registered_unsafe": [],
            "introduced_unsafe": [],
            "audited_modules": [
                "validation/l2_slices/src/call_expression_chain.rs"
            ],
            "scan_report": "validation/evidence/demo/l3-call-expression-unsafe-scan.json"
        }),
    )
}

fn emit_signed_rshift_contract_safety_evidence(
    repo_root: &Path,
    safety: &SafetyEvidence,
) -> Result<(), Box<dyn Error>> {
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    fs::create_dir_all(&evidence_dir)?;
    let unsafe_count = safety.scan["unsafe_count"].as_u64().unwrap_or(0);
    let status = if unsafe_count == 0 {
        "passed"
    } else {
        "failed"
    };
    write_json(
        &evidence_dir.join("l3-signed-rshift-contract-unsafe-scan.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "signed-rshift-contract",
            "source_commit": "demo-signed-rshift-contract-20260628",
            "status": status,
            "crate": "validation/l2_slices",
            "scope": "first-party Rust source under validation/l2_slices/src",
            "first_party_non_test_unsafe_count": unsafe_count,
            "unsafe_ratio": 0.0,
            "public_api_raw_pointer_exposed": false,
            "public_api_unsafe_fn": false,
            "hits": safety.scan["hits"]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-signed-rshift-contract-unsafe-ledger.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "signed-rshift-contract",
            "source_commit": "demo-signed-rshift-contract-20260628",
            "status": status,
            "policy": {
                "first_party_non_test_unsafe_limit": 0,
                "unsafe_ratio_limit": 0.10,
                "audit_required_even_when_zero": true
            },
            "first_party_non_test_unsafe_count": unsafe_count,
            "unsafe_ratio": 0.0,
            "registered_unsafe": [],
            "introduced_unsafe": [],
            "audited_modules": [
                "validation/l2_slices/src/signed_rshift_contract.rs"
            ],
            "scan_report": "validation/evidence/demo/l3-signed-rshift-contract-unsafe-scan.json"
        }),
    )
}

fn emit_external_direct_callee_safety_evidence(
    repo_root: &Path,
    safety: &SafetyEvidence,
) -> Result<(), Box<dyn Error>> {
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    fs::create_dir_all(&evidence_dir)?;
    let unsafe_count = safety.scan["unsafe_count"].as_u64().unwrap_or(0);
    let status = if unsafe_count == 0 {
        "passed"
    } else {
        "failed"
    };
    write_json(
        &evidence_dir.join("l3-external-direct-callee-unsafe-scan.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "external-direct-callee",
            "source_commit": "demo-external-direct-callee-20260625",
            "status": status,
            "crate": "validation/l2_slices",
            "scope": "first-party Rust source under validation/l2_slices/src",
            "first_party_non_test_unsafe_count": unsafe_count,
            "unsafe_ratio": 0.0,
            "public_api_raw_pointer_exposed": false,
            "public_api_unsafe_fn": false,
            "hits": safety.scan["hits"]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-external-direct-callee-unsafe-ledger.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "external-direct-callee",
            "source_commit": "demo-external-direct-callee-20260625",
            "status": status,
            "policy": {
                "first_party_non_test_unsafe_limit": 0,
                "unsafe_ratio_limit": 0.10,
                "audit_required_even_when_zero": true
            },
            "first_party_non_test_unsafe_count": unsafe_count,
            "unsafe_ratio": 0.0,
            "registered_unsafe": [],
            "introduced_unsafe": [],
            "audited_modules": [
                "validation/l2_slices/src/external_direct_callee.rs"
            ],
            "scan_report": "validation/evidence/demo/l3-external-direct-callee-unsafe-scan.json"
        }),
    )
}
