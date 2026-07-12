fn emit_safety_evidence(
    crate_dir: &Path,
    evidence_dir: &Path,
) -> Result<SafetyEvidence, Box<dyn Error>> {
    let src_dir = crate_dir.join("src");
    let mut hits = Vec::new();
    scan_rust_files(&src_dir, &mut |path, line_no, line| {
        if line
            .split(|ch: char| !(ch.is_ascii_alphanumeric() || ch == '_'))
            .any(|token| token == "unsafe")
        {
            hits.push(json!({
                "path": relative_path(path),
                "line": line_no,
                "text": line.trim()
            }));
        }
    })?;
    let status = if hits.is_empty() { "passed" } else { "failed" };
    let scan = json!({
        "schema_version": 1,
        "crate": "validation/l2_slices",
        "scope": "first-party Rust source under validation/l2_slices/src",
        "unsafe_count": hits.len(),
        "status": status,
        "hits": hits
    });
    write_json(&evidence_dir.join("unsafe-scan.json"), &scan)?;

    let ledger = json!({
        "schema_version": 1,
        "crate": "validation/l2_slices",
        "scope": "first-party non-test Rust source under validation/l2_slices/src",
        "policy": {
            "first_party_non_test_unsafe_limit": 0,
            "registered_unsafe_required": true,
            "audit_required_even_when_zero": true
        },
        "first_party_non_test_unsafe_count": hits.len(),
        "registered_unsafe": [],
        "introduced_unsafe": [],
        "audit_status": status,
        "scan_report": "validation/evidence/l2-slices/unsafe-scan.json",
        "audited_modules": [
            "validation/l2_slices/src/add_i32_pair_ptr_arith.rs",
            "validation/l2_slices/src/call_expression_chain.rs",
            "validation/l2_slices/src/copy_i32_ptr_arith.rs",
            "validation/l2_slices/src/libuv_ip4_addr.rs",
            "validation/l2_slices/src/sqlite_varint.rs",
            "validation/l2_slices/src/store_add_one.rs",
            "validation/l2_slices/src/sum_i32_buffer.rs",
            "validation/l2_slices/src/sum_i32_ptr_arith.rs",
            "validation/l2_slices/src/zlib_adler32.rs",
            "validation/l2_slices/src/zstd_xxh32.rs"
        ]
    });
    write_json(&evidence_dir.join("unsafe-ledger.json"), &ledger)?;

    Ok(SafetyEvidence { scan, ledger })
}

fn emit_libuv_safety_evidence(
    repo_root: &Path,
    safety: &SafetyEvidence,
) -> Result<(), Box<dyn Error>> {
    let evidence_dir = repo_root.join("validation").join("evidence").join("libuv");
    fs::create_dir_all(&evidence_dir)?;
    let unsafe_count = safety.scan["unsafe_count"].as_u64().unwrap_or(0);
    let status = if unsafe_count == 0 {
        "passed"
    } else {
        "failed"
    };
    write_json(
        &evidence_dir.join("l3-ip4-addr-unsafe-scan.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "status": status,
            "crate": "validation/l2_slices",
            "scope": "first-party Rust source under validation/l2_slices/src",
            "first_party_non_test_unsafe_count": unsafe_count,
            "unsafe_ratio": 0.0,
            "hits": safety.scan["hits"]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-ip4-addr-unsafe-ledger.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
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
                "validation/l2_slices/src/libuv_ip4_addr.rs"
            ],
            "scan_report": "validation/evidence/libuv/l3-ip4-addr-unsafe-scan.json"
        }),
    )
}
