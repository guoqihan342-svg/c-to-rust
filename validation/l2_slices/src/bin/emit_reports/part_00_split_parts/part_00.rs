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
