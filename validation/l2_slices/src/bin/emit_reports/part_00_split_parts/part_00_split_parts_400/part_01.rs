#[derive(Debug, Deserialize)]
struct FdbKvSetOracleReport {
    level: String,
    target_id: String,
    slice_id: String,
    source_commit: String,
    source_boundary: Value,
    compared_fields: Vec<String>,
    case_count: usize,
    cases: Vec<FdbKvSetOracleCase>,
}

#[derive(Debug, Deserialize)]
struct FdbKvSetOracleCase {
    id: String,
    coverage_kind: String,
    db_name: String,
    db_state: String,
    key: String,
    value: Option<String>,
    return_code: i32,
    expected_outputs: FdbKvSetExpectedOutputs,
    status: String,
}

#[derive(Debug, Deserialize)]
struct FdbKvSetExpectedOutputs {
    return_code: i32,
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
    emit_real_fdb_kv_to_blob(&fixtures_dir, repo_root)?;
    emit_real_fdb_tsl_to_blob(&fixtures_dir, repo_root)?;
    emit_real_fdb_is_str(&fixtures_dir, repo_root)?;
    emit_real_fdb_kv_del(&fixtures_dir, repo_root)?;
    emit_real_fdb_kv_set(&fixtures_dir, repo_root)?;
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
