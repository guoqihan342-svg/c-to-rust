fn emit_summary(
    evidence_dir: &Path,
    slices: &[SliceResult],
    safety: &SafetyEvidence,
    negative_diffs: &[NegativeDiffResult],
) -> Result<(), Box<dyn Error>> {
    let negative_diffs_passed =
        !negative_diffs.is_empty() && negative_diffs.iter().all(|diff| diff.status == "passed");
    let all_passed = slices
        .iter()
        .all(|slice| slice.l2_status == "passed" && slice.l3_status == "passed")
        && safety.scan["status"] == "passed"
        && safety.ledger["audit_status"] == "passed"
        && negative_diffs_passed;
    write_json(
        &evidence_dir.join("l2-l3-summary.json"),
        &json!({
            "schema_version": 1,
            "status": if all_passed { "passed" } else { "failed" },
            "rust_check": {
                "command": "cargo test",
                "status": if slices.iter().all(|slice| slice.l2_status == "passed") { "passed" } else { "failed" },
                "tested_modules": [
                    "validation/l2_slices/src/add_i32_pair_ptr_arith.rs",
                    "validation/l2_slices/src/call_expression_chain.rs",
                    "validation/l2_slices/src/copy_i32_ptr_arith.rs",
                    "validation/l2_slices/src/libuv_ip4_addr.rs",
                    "validation/l2_slices/src/signed_rshift_contract.rs",
                    "validation/l2_slices/src/sqlite_varint.rs",
                    "validation/l2_slices/src/store_add_one.rs",
                    "validation/l2_slices/src/sum_i32_buffer.rs",
                    "validation/l2_slices/src/sum_i32_ptr_arith.rs",
                    "validation/l2_slices/src/zlib_adler32.rs",
                    "validation/l2_slices/src/zstd_xxh32.rs"
                ]
            },
            "diff_check": {
                "status": if slices.iter().all(|slice| slice.l3_status == "passed") { "passed" } else { "failed" },
                "slices": slices.iter().map(|slice| {
                    json!({
                        "slice_id": slice.slice_id,
                        "case_count": slice.case_count,
                        "l2_status": slice.l2_status,
                        "l3_status": slice.l3_status
                    })
                }).collect::<Vec<_>>()
            },
            "safety_check": &safety.scan,
            "unsafe_ledger_check": &safety.ledger,
            "negative_diff_check": {
                "status": if negative_diffs_passed { "passed" } else { "failed" },
                "reports": negative_diffs.iter().map(|diff| {
                    json!({
                        "slice_id": diff.slice_id,
                        "status": diff.status,
                        "report": diff.report_path
                    })
                }).collect::<Vec<_>>()
            },
            "reporting_boundary": "This success applies only to the named slice functions, pinned upstream commits, and committed fixture input domains. It does not prove full-project migration or global semantic equivalence."
        }),
    )
}

fn read_json<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<T, Box<dyn Error>> {
    let text = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&text)?)
}

fn required_json_value<'a>(
    value: &'a Value,
    pointer: &str,
    context: &str,
) -> Result<&'a Value, Box<dyn Error>> {
    value
        .pointer(pointer)
        .ok_or_else(|| format!("{context} missing required JSON pointer {pointer}").into())
}
