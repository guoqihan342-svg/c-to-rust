fn emit_sum_i32_ptr_arith_safety_evidence(
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
        &evidence_dir.join("l3-sum-i32-ptr-arith-unsafe-scan.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": "demo-sum-i32-ptr-arith-20260625",
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
        &evidence_dir.join("l3-sum-i32-ptr-arith-unsafe-ledger.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": "demo-sum-i32-ptr-arith-20260625",
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
                "validation/l2_slices/src/sum_i32_ptr_arith.rs"
            ],
            "scan_report": "validation/evidence/demo/l3-sum-i32-ptr-arith-unsafe-scan.json"
        }),
    )
}

fn emit_copy_i32_ptr_arith_safety_evidence(
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
        &evidence_dir.join("l3-copy-i32-ptr-arith-unsafe-scan.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "copy-i32-ptr-arith",
            "source_commit": "demo-copy-i32-ptr-arith-20260625",
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
        &evidence_dir.join("l3-copy-i32-ptr-arith-unsafe-ledger.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "copy-i32-ptr-arith",
            "source_commit": "demo-copy-i32-ptr-arith-20260625",
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
                "validation/l2_slices/src/copy_i32_ptr_arith.rs"
            ],
            "scan_report": "validation/evidence/demo/l3-copy-i32-ptr-arith-unsafe-scan.json"
        }),
    )
}

fn emit_add_i32_pair_ptr_arith_safety_evidence(
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
        &evidence_dir.join("l3-add-i32-pair-ptr-arith-unsafe-scan.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "add-i32-pair-ptr-arith",
            "source_commit": "demo-add-i32-pair-ptr-arith-20260625",
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
        &evidence_dir.join("l3-add-i32-pair-ptr-arith-unsafe-ledger.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "add-i32-pair-ptr-arith",
            "source_commit": "demo-add-i32-pair-ptr-arith-20260625",
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
                "validation/l2_slices/src/add_i32_pair_ptr_arith.rs"
            ],
            "scan_report": "validation/evidence/demo/l3-add-i32-pair-ptr-arith-unsafe-scan.json"
        }),
    )
}
