#[derive(Debug, Deserialize)]
struct SqliteVarintCase {
    id: String,
    value: u64,
    encoded_hex: String,
    bytes_used: usize,
    decoded_value: u64,
    decoded_bytes: usize,
}

#[derive(Debug, Deserialize)]
struct ChecksumCase {
    id: String,
    input_hex: String,
    seed: Option<u32>,
    value: u32,
}

#[derive(Debug, Deserialize)]
struct LibuvIp4OracleReport {
    cases: Vec<LibuvIp4OracleCase>,
}

#[derive(Debug, Deserialize)]
struct LibuvIp4OracleCase {
    id: String,
    ip: String,
    port: i32,
    coverage_kind: String,
    return_code: i32,
    status: String,
    family: u16,
    port_host: u16,
    port_bytes_hex: String,
    addr_bytes_hex: String,
}

#[derive(Debug, Deserialize)]
struct StoreAddOneOracleReport {
    cases: Vec<StoreAddOneOracleCase>,
}

#[derive(Debug, Deserialize)]
struct StoreAddOneOracleCase {
    id: String,
    coverage_kind: String,
    value: i32,
    return_code: i32,
    status: String,
    out0: i32,
}

#[derive(Debug, Deserialize)]
struct SumI32BufferOracleReport {
    cases: Vec<SumI32BufferOracleCase>,
}

#[derive(Debug, Deserialize)]
struct SumI32BufferOracleCase {
    id: String,
    coverage_kind: String,
    values: Vec<i32>,
    len: i32,
    return_code: i32,
    status: String,
    sum: i32,
    source_reads: String,
    source_write: String,
}

#[derive(Debug, Deserialize)]
struct CallExpressionChainOracleReport {
    cases: Vec<CallExpressionChainOracleCase>,
}

#[derive(Debug, Deserialize)]
struct CallExpressionChainOracleCase {
    id: String,
    coverage_kind: String,
    input_value: i32,
    return_value: i32,
    status: String,
    call_expression_count: usize,
    call_expression_contexts: Vec<String>,
    source_calls: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct SignedRshiftContractOracleReport {
    cases: Vec<SignedRshiftContractOracleCase>,
}

#[derive(Debug, Deserialize)]
struct SignedRshiftContractOracleCase {
    id: String,
    coverage_kind: String,
    value: i32,
    count: u32,
    return_value: i32,
    status: String,
    contract: String,
}

#[derive(Debug, Deserialize)]
struct ExternalDirectCalleeOracleReport {
    cases: Vec<ExternalDirectCalleeOracleCase>,
}

#[derive(Debug, Deserialize)]
struct ExternalDirectCalleeOracleCase {
    id: String,
    coverage_kind: String,
    input_value: i32,
    return_value: i32,
    status: String,
    external_callee_call_count: usize,
    external_callee_contexts: Vec<String>,
    external_callee_bindings: Vec<String>,
    source_calls: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct SumI32PtrArithOracleReport {
    cases: Vec<SumI32PtrArithOracleCase>,
}

#[derive(Debug, Deserialize)]
struct SumI32PtrArithOracleCase {
    id: String,
    coverage_kind: String,
    values: Vec<i32>,
    len: i32,
    return_code: i32,
    status: String,
    sum: i32,
    source_reads: String,
    canonical_reads: String,
    source_write: String,
}

#[derive(Debug, Deserialize)]
struct CopyI32PtrArithOracleReport {
    cases: Vec<CopyI32PtrArithOracleCase>,
}

#[derive(Debug, Deserialize)]
struct CopyI32PtrArithOracleCase {
    id: String,
    coverage_kind: String,
    values: Vec<i32>,
    len: i32,
    return_code: i32,
    status: String,
    out_values: Vec<i32>,
    source_reads: String,
    canonical_reads: String,
    source_writes: String,
    canonical_writes: String,
    write_count: usize,
}

#[derive(Debug, Deserialize)]
struct AddI32PairPtrArithOracleReport {
    cases: Vec<AddI32PairPtrArithOracleCase>,
}

#[derive(Debug, Deserialize)]
struct AddI32PairPtrArithOracleCase {
    id: String,
    coverage_kind: String,
    lhs: Vec<i32>,
    rhs: Vec<i32>,
    len: i32,
    return_code: i32,
    status: String,
    out_values: Vec<i32>,
    source_reads: String,
    canonical_reads: String,
    source_writes: String,
    canonical_writes: String,
    write_count: usize,
    safe_noalias_precondition: bool,
    alias_case: String,
    alias_matrix: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct FdbCalcCrc32OracleReport {
    level: String,
    target_id: String,
    slice_id: String,
    source_boundary: Value,
    compared_fields: Vec<String>,
    case_count: usize,
    cases: Vec<FdbCalcCrc32OracleCase>,
}

#[derive(Debug, Deserialize)]
struct FdbCalcCrc32OracleCase {
    id: String,
    coverage_kind: String,
    crc: u32,
    buf: Vec<u8>,
    size: usize,
    return_code: u32,
    status: String,
}

#[derive(Debug, Deserialize)]
struct FdbBlobMakeOracleReport {
    level: String,
    target_id: String,
    slice_id: String,
    source_commit: String,
    source_boundary: Value,
    compared_fields: Vec<String>,
    case_count: usize,
    cases: Vec<FdbBlobMakeOracleCase>,
}

#[derive(Debug, Deserialize)]
struct FdbBlobMakeOracleCase {
    id: String,
    coverage_kind: String,
    buf_len: usize,
    initial_blob_size: usize,
    value_buf: Option<Vec<u8>>,
    expected_outputs: FdbBlobMakeExpectedOutputs,
    status: String,
}

#[derive(Debug, Deserialize)]
struct FdbBlobMakeExpectedOutputs {
    #[serde(rename = "return_same_blob")]
    return_same_blob: bool,
    #[serde(rename = "blob.buf")]
    blob_buf: String,
    #[serde(rename = "blob.size")]
    blob_size: usize,
}

#[derive(Debug)]
struct SliceResult {
    slice_id: &'static str,
    case_count: usize,
    l2_status: &'static str,
    l3_status: &'static str,
}

#[derive(Debug)]
struct SafetyEvidence {
    scan: Value,
    ledger: Value,
}

#[derive(Debug)]
struct NegativeDiffResult {
    slice_id: &'static str,
    status: &'static str,
    report_path: &'static str,
}

struct L2TestTranslationSpec<'a> {
    evidence_dir: &'a Path,
    target_id: &'a str,
    slice_id: &'a str,
    source_commit: &'a str,
    fixture_path: &'a Path,
    rust_test_name: &'a str,
    main_paths: &'a [&'a str],
    error_paths: &'a [&'a str],
    negative_cases: &'a [&'a str],
    behavior_fields: &'a [&'a str],
}

struct L3TestTranslationSpec<'a> {
    evidence_dir: &'a Path,
    slice_id: &'a str,
    source_commit: &'a str,
    fixture_path: &'a Path,
    rust_test_name: &'a str,
    main_paths: &'a [&'a str],
    negative_cases: &'a [&'a str],
    behavior_fields: &'a [&'a str],
}

fn main() -> Result<(), Box<dyn Error>> {
    let crate_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = crate_dir
        .parent()
        .and_then(Path::parent)
        .ok_or("crate path must be under validation/l2_slices")?;
    let fixtures_dir = crate_dir.join("fixtures");
    let evidence_dir = repo_root
        .join("validation")
        .join("evidence")
        .join("l2-slices");
    fs::create_dir_all(&evidence_dir)?;

    let slices = vec![
        emit_sqlite_varint(&fixtures_dir, &evidence_dir)?,
        emit_zlib_adler32(&fixtures_dir, &evidence_dir)?,
        emit_zstd_xxh32(&fixtures_dir, &evidence_dir)?,
        emit_libuv_ip4_addr(&fixtures_dir, repo_root)?,
        emit_store_add_one(&fixtures_dir, repo_root)?,
        emit_sum_i32_buffer(&fixtures_dir, repo_root)?,
        emit_call_expression_chain(&fixtures_dir, repo_root)?,
        emit_signed_rshift_contract(&fixtures_dir, repo_root)?,
        emit_external_direct_callee(&fixtures_dir, repo_root)?,
        emit_sum_i32_ptr_arith(&fixtures_dir, repo_root)?,
        emit_copy_i32_ptr_arith(&fixtures_dir, repo_root)?,
        emit_add_i32_pair_ptr_arith(&fixtures_dir, repo_root)?,
    ];
    emit_real_fdb_calc_crc32(&fixtures_dir, repo_root)?;
    emit_real_fdb_blob_make(&fixtures_dir, repo_root)?;
    let safety = emit_safety_evidence(&crate_dir, &evidence_dir)?;
    emit_libuv_safety_evidence(repo_root, &safety)?;
    emit_store_add_one_safety_evidence(repo_root, &safety)?;
    emit_sum_i32_buffer_safety_evidence(repo_root, &safety)?;
    emit_call_expression_chain_safety_evidence(repo_root, &safety)?;
    emit_signed_rshift_contract_safety_evidence(repo_root, &safety)?;
    emit_external_direct_callee_safety_evidence(repo_root, &safety)?;
    emit_sum_i32_ptr_arith_safety_evidence(repo_root, &safety)?;
    emit_copy_i32_ptr_arith_safety_evidence(repo_root, &safety)?;
    emit_add_i32_pair_ptr_arith_safety_evidence(repo_root, &safety)?;
    let mut negative_diffs = emit_negative_diffs(&fixtures_dir, &evidence_dir)?;
    negative_diffs.push(emit_libuv_negative_diff(&fixtures_dir, repo_root)?);
    negative_diffs.push(emit_store_add_one_negative_diff(&fixtures_dir, repo_root)?);
    negative_diffs.push(emit_sum_i32_buffer_negative_diff(&fixtures_dir, repo_root)?);
    negative_diffs.push(emit_call_expression_chain_negative_diff(
        &fixtures_dir,
        repo_root,
    )?);
    negative_diffs.push(emit_signed_rshift_contract_negative_diff(
        &fixtures_dir,
        repo_root,
    )?);
    negative_diffs.push(emit_external_direct_callee_negative_diff(
        &fixtures_dir,
        repo_root,
    )?);
    negative_diffs.push(emit_sum_i32_ptr_arith_negative_diff(
        &fixtures_dir,
        repo_root,
    )?);
    negative_diffs.push(emit_copy_i32_ptr_arith_negative_diff(
        &fixtures_dir,
        repo_root,
    )?);
    negative_diffs.push(emit_add_i32_pair_ptr_arith_negative_diff(
        &fixtures_dir,
        repo_root,
    )?);
    let sum_slice = slices
        .iter()
        .find(|slice| slice.slice_id == "demo-sum-i32-buffer")
        .ok_or("demo-sum-i32-buffer slice result must be present")?;
    let sum_unsafe_status =
        if safety.scan["status"] == "passed" && safety.ledger["audit_status"] == "passed" {
            "passed"
        } else {
            "failed"
        };
    let sum_manifest_status = if sum_slice.l3_status == "passed" && sum_unsafe_status == "passed" {
        "passed"
    } else {
        "failed"
    };
    emit_sum_i32_buffer_static_l3_evidence(
        &repo_root.join("validation").join("evidence").join("demo"),
        sum_slice.case_count,
        sum_manifest_status,
        sum_unsafe_status,
    )?;
    let call_slice = slices
        .iter()
        .find(|slice| slice.slice_id == "demo-call-expression")
        .ok_or("demo-call-expression slice result must be present")?;
    let call_manifest_status = if call_slice.l3_status == "passed" && sum_unsafe_status == "passed"
    {
        "passed"
    } else {
        "failed"
    };
    emit_call_expression_chain_static_l3_evidence(
        &repo_root.join("validation").join("evidence").join("demo"),
        call_slice.case_count,
        call_manifest_status,
        sum_unsafe_status,
    )?;
    let signed_rshift_slice = slices
        .iter()
        .find(|slice| slice.slice_id == "demo-signed-rshift-contract")
        .ok_or("demo-signed-rshift-contract slice result must be present")?;
    let signed_rshift_manifest_status =
        if signed_rshift_slice.l3_status == "passed" && sum_unsafe_status == "passed" {
            "passed"
        } else {
            "failed"
        };
    emit_signed_rshift_contract_static_l3_evidence(
        &repo_root.join("validation").join("evidence").join("demo"),
        signed_rshift_slice.case_count,
        signed_rshift_manifest_status,
        sum_unsafe_status,
    )?;
    let external_callee_slice = slices
        .iter()
        .find(|slice| slice.slice_id == "demo-external-direct-callee")
        .ok_or("demo-external-direct-callee slice result must be present")?;
    let external_callee_manifest_status =
        if external_callee_slice.l3_status == "passed" && sum_unsafe_status == "passed" {
            "passed"
        } else {
            "failed"
        };
    emit_external_direct_callee_static_l3_evidence(
        &repo_root.join("validation").join("evidence").join("demo"),
        external_callee_slice.case_count,
        external_callee_manifest_status,
        sum_unsafe_status,
    )?;
    let ptr_arith_slice = slices
        .iter()
        .find(|slice| slice.slice_id == "demo-sum-i32-ptr-arith")
        .ok_or("demo-sum-i32-ptr-arith slice result must be present")?;
    let ptr_arith_manifest_status =
        if ptr_arith_slice.l3_status == "passed" && sum_unsafe_status == "passed" {
            "passed"
        } else {
            "failed"
        };
    emit_sum_i32_ptr_arith_static_l3_evidence(
        &repo_root.join("validation").join("evidence").join("demo"),
        ptr_arith_slice.case_count,
        ptr_arith_manifest_status,
        sum_unsafe_status,
    )?;
    emit_summary(&evidence_dir, &slices, &safety, &negative_diffs)?;

    Ok(())
}

fn emit_real_fdb_calc_crc32(fixtures_dir: &Path, repo_root: &Path) -> Result<(), Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("real-fdb-calc-crc32.json");
    let report: FdbCalcCrc32OracleReport = read_json(&fixture_path)?;
    if report.case_count != report.cases.len() {
        return Err(format!(
            "real-fdb-calc-crc32 case_count {} does not match {} fixture cases",
            report.case_count,
            report.cases.len()
        )
        .into());
    }

    let evidence_dir = repo_root
        .join("validation")
        .join("evidence")
        .join("flashdb");
    fs::create_dir_all(&evidence_dir)?;
    let slice_spec_path = repo_root
        .join("validation")
        .join("slice-specs")
        .join("flashdb-real-fdb-calc-crc32.json");
    let oracle_status_path = evidence_dir
        .join("auto-translation")
        .join("real-fdb-calc-crc32")
        .join("l3-real-fdb-calc-crc32-c-oracle-status.json");
    let slice_spec: Value = read_json(&slice_spec_path)?;
    let oracle_status: Value = read_json(&oracle_status_path)?;
    let source_file_hashes = required_json_value(
        &slice_spec,
        "/source/source_file_hashes",
        "real-fdb slice spec",
    )?
    .clone();
    let source_span_sha256 = required_json_value(
        &slice_spec,
        "/c_boundary/signatures/0/source_span/sha256",
        "real-fdb slice spec",
    )?
    .clone();
    let source_commit = required_json_value(&slice_spec, "/source_commit", "real-fdb slice spec")?.clone();
    let fixture_sha256 = oracle_status
        .pointer("/fixture_sha256")
        .cloned()
        .unwrap_or(json!(sha256_hex(&fixture_path)?));
    let global_dependencies = required_json_value(
        &oracle_status,
        "/global_linkage_requirements",
        "real-fdb c oracle status",
    )?
    .clone();
    let harness_draft_ref = required_json_value(
        &oracle_status,
        "/harness_draft_ref",
        "real-fdb c oracle status",
    )?
    .clone();
    let compile_execution = json!({
        "status": required_json_value(&oracle_status, "/compile_execution/status", "real-fdb c oracle status")?.clone(),
        "semantic_pass": required_json_value(&oracle_status, "/compile_execution/semantic_pass", "real-fdb c oracle status")?.clone(),
        "toolchain_adapter": required_json_value(&oracle_status, "/compile_execution/toolchain_adapter", "real-fdb c oracle status")?.clone(),
        "toolchain_status_after_attempt": required_json_value(
            &oracle_status,
            "/compile_execution/toolchain_status_after_attempt",
            "real-fdb c oracle status",
        )?.clone()
    });

    let mut rust_cases = Vec::with_capacity(report.cases.len());
    let mut first_mismatch = None;
    for case in &report.cases {
        if case.buf.len() != case.size {
            return Err(format!(
                "real-fdb-calc-crc32 case {} size {} does not match {} bytes",
                case.id,
                case.size,
                case.buf.len()
            )
            .into());
        }
        let actual = fdb_calc_crc32::fdb_calc_crc32(case.crc, &case.buf);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "return_code",
            json!(case.return_code),
            json!(actual),
        );
        rust_cases.push(json!({
            "id": case.id,
            "coverage_kind": case.coverage_kind,
            "crc": case.crc,
            "buf": case.buf,
            "size": case.size,
            "return_code": actual,
            "status": case.status
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    let prefix = "l3-real-fdb-calc-crc32";
    let c_oracle_cases: Vec<Value> = report
        .cases
        .iter()
        .map(|case| {
            json!({
                "id": case.id,
                "return_code": case.return_code,
                "status": "passed"
            })
        })
        .collect();
    write_json(
        &evidence_dir.join(format!("{prefix}-c-oracle.json")),
        &json!({
            "schema_version": 1,
            "level": report.level,
            "target_id": report.target_id,
            "slice_id": report.slice_id,
            "status": "passed",
            "semantic_pass": true,
            "toolchain_status": "C_ORACLE_GENERATED",
            "source_commit": source_commit.clone(),
            "source_boundary": report.source_boundary,
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports",
            "generator": "validation/l2_slices/src/bin/emit_reports.rs::emit_real_fdb_calc_crc32",
            "case_count": report.case_count,
            "compared_fields": report.compared_fields,
            "provenance": {
                "fixture_sha256": fixture_sha256,
                "source_file_hashes": source_file_hashes,
                "source_span_sha256": source_span_sha256,
                "global_dependencies": global_dependencies,
                "harness_draft_ref": harness_draft_ref,
                "compile_execution": compile_execution,
                "evidence_refs": {
                    "slice_spec": relative_path(&slice_spec_path),
                    "c_oracle_status": relative_path(&oracle_status_path),
                    "version_manifest": "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-version-manifest.json",
                    "evidence_manifest": "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-evidence-manifest.json"
                },
                "cycle_boundary": "This provenance intentionally omits the root c-oracle self hash; auto-translation evidence records the accepted c-oracle hash after regeneration."
            },
            "cases": c_oracle_cases,
            "accepted_boundary": "Accepted C oracle report is bound to the fixture cases and WSL compile/harness evidence captured by the auto-translation oracle draft; generated Rust draft remains non-authoritative."
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-rust-report.json")),
        &json!({
            "schema_version": 1,
            "level": report.level,
            "target_id": report.target_id,
            "slice_id": report.slice_id,
            "source_commit": source_commit.clone(),
            "source_boundary": report.source_boundary,
            "rust_module_path": "validation/l2_slices/src/fdb_calc_crc32.rs",
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports",
            "status": status,
            "case_count": report.case_count,
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-diff.json")),
        &json!({
            "schema_version": 1,
            "level": report.level,
            "target_id": report.target_id,
            "slice_id": report.slice_id,
            "source_commit": source_commit.clone(),
            "status": status,
            "case_count": report.case_count,
            "compared_fields": report.compared_fields,
            "first_mismatch": first_mismatch
        }),
    )?;
    write_real_fdb_calc_crc32_negative_diff(&report, &evidence_dir, &source_commit)?;

    Ok(())
}

fn write_real_fdb_calc_crc32_negative_diff(
    report: &FdbCalcCrc32OracleReport,
    evidence_dir: &Path,
    source_commit: &Value,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .first()
        .ok_or("real-fdb-calc-crc32 fixture must include at least one case")?;
    let actual = fdb_calc_crc32::fdb_calc_crc32(case.crc, &case.buf);
    let mutated_return_code = case.return_code.wrapping_add(1);
    let detected = mutated_return_code != actual;
    write_json(
        &evidence_dir.join("l3-real-fdb-calc-crc32-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": report.level,
            "target_id": report.target_id,
            "slice_id": report.slice_id,
            "source_commit": source_commit.clone(),
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "first oracle case return_code is changed by wrapping +1",
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "return_code",
                    "mutated_c_value": mutated_return_code,
                    "rust_value": actual
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}

