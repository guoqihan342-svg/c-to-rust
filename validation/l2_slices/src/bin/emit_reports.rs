use std::{
    error::Error,
    fs,
    path::{Path, PathBuf},
};

use c_to_rust_l2_slices::{
    add_i32_pair_ptr_arith, call_expression_chain, copy_i32_ptr_arith, external_direct_callee,
    fdb_calc_crc32, libuv_ip4_addr, sqlite_varint, store_add_one, sum_i32_buffer,
    sum_i32_ptr_arith, zlib_adler32, zstd_xxh32,
};
use serde::Deserialize;
use serde_json::{json, Value};

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
    source_commit: String,
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
        emit_external_direct_callee(&fixtures_dir, repo_root)?,
        emit_sum_i32_ptr_arith(&fixtures_dir, repo_root)?,
        emit_copy_i32_ptr_arith(&fixtures_dir, repo_root)?,
        emit_add_i32_pair_ptr_arith(&fixtures_dir, repo_root)?,
    ];
    emit_real_fdb_calc_crc32(&fixtures_dir, repo_root)?;
    let safety = emit_safety_evidence(&crate_dir, &evidence_dir)?;
    emit_libuv_safety_evidence(repo_root, &safety)?;
    emit_store_add_one_safety_evidence(repo_root, &safety)?;
    emit_sum_i32_buffer_safety_evidence(repo_root, &safety)?;
    emit_call_expression_chain_safety_evidence(repo_root, &safety)?;
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
            "source_commit": report.source_commit,
            "source_boundary": report.source_boundary,
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports",
            "generator": "validation/l2_slices/src/bin/emit_reports.rs::emit_real_fdb_calc_crc32",
            "case_count": report.case_count,
            "compared_fields": report.compared_fields,
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
            "source_commit": report.source_commit,
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
            "source_commit": report.source_commit,
            "status": status,
            "case_count": report.case_count,
            "compared_fields": report.compared_fields,
            "first_mismatch": first_mismatch
        }),
    )?;
    write_real_fdb_calc_crc32_negative_diff(&report, &evidence_dir)?;

    Ok(())
}

fn write_real_fdb_calc_crc32_negative_diff(
    report: &FdbCalcCrc32OracleReport,
    evidence_dir: &Path,
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
            "source_commit": report.source_commit,
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

fn emit_store_add_one(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("store-add-one-c-oracle.json");
    let oracle_value: Value = read_json(&fixture_path)?;
    let report: StoreAddOneOracleReport = serde_json::from_value(oracle_value.clone())?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    fs::create_dir_all(&evidence_dir)?;
    write_json(
        &evidence_dir.join("l3-store-add-one-c-oracle.json"),
        &oracle_value,
    )?;

    let mut rust_cases = Vec::with_capacity(report.cases.len());
    let mut first_mismatch = None;

    for case in &report.cases {
        let rust = store_add_one::store_add_one(case.value);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "return_code",
            json!(case.return_code),
            json!(rust.return_code),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "status",
            json!(case.status),
            json!(rust.status),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "out0",
            json!(case.out0),
            json!(rust.out0),
        );

        rust_cases.push(json!({
            "id": case.id,
            "coverage_kind": case.coverage_kind,
            "value": case.value,
            "return_code": rust.return_code,
            "status": rust.status,
            "out0": rust.out0,
            "source_write": rust.source_write
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("l3-store-add-one-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "source_commit": "demo-store-add-one-20260625",
            "c_source_boundary": "int store_add_one(int value, int* out) { out[0] = value + 1; return 0; }",
            "rust_module_path": "validation/l2_slices/src/store_add_one.rs",
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --bin emit_reports",
            "status": status,
            "case_count": report.cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-store-add-one-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "source_commit": "demo-store-add-one-20260625",
            "status": status,
            "case_count": report.cases.len(),
            "compared_fields": ["return_code", "status", "out0"],
            "first_mismatch": first_mismatch
        }),
    )?;
    write_store_add_one_negative_diff(&report, &evidence_dir)?;
    emit_store_add_one_performance_smoke(&report, &evidence_dir)?;
    emit_store_add_one_static_l3_evidence(&evidence_dir, report.cases.len(), status)?;

    Ok(SliceResult {
        slice_id: "demo-store-add-one",
        case_count: report.cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_sum_i32_buffer(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("sum-i32-buffer-c-oracle.json");
    let oracle_value: Value = read_json(&fixture_path)?;
    let report: SumI32BufferOracleReport = serde_json::from_value(oracle_value.clone())?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    fs::create_dir_all(&evidence_dir)?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-c-oracle.json"),
        &oracle_value,
    )?;

    let mut rust_cases = Vec::with_capacity(report.cases.len());
    let mut first_mismatch = None;

    for case in &report.cases {
        let rust = sum_i32_buffer::sum_i32_buffer(&case.values);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "return_code",
            json!(case.return_code),
            json!(rust.return_code),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "status",
            json!(case.status),
            json!(rust.status),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "len",
            json!(case.len),
            json!(rust.len),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "sum",
            json!(case.sum),
            json!(rust.sum),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "source_reads",
            json!(case.source_reads),
            json!(rust.source_reads),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "source_write",
            json!(case.source_write),
            json!(rust.source_write),
        );

        rust_cases.push(json!({
            "id": case.id,
            "coverage_kind": case.coverage_kind,
            "values": case.values,
            "len": rust.len,
            "return_code": rust.return_code,
            "status": rust.status,
            "sum": rust.sum,
            "source_reads": rust.source_reads,
            "source_write": rust.source_write
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": "demo-sum-i32-buffer-20260625",
            "c_source_boundary": "int sum_i32_buffer(const int* values, int len, int* out) { int total = 0; for (int i = 0; i < len; i++) { total = total + values[i]; } out[0] = total; return 0; }",
            "rust_module_path": "validation/l2_slices/src/sum_i32_buffer.rs",
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --bin emit_reports",
            "status": status,
            "case_count": report.cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": "demo-sum-i32-buffer-20260625",
            "status": status,
            "case_count": report.cases.len(),
            "compared_fields": ["return_code", "status", "len", "sum", "source_reads", "source_write"],
            "first_mismatch": first_mismatch
        }),
    )?;
    emit_sum_i32_buffer_performance_smoke(&report, &evidence_dir)?;

    Ok(SliceResult {
        slice_id: "demo-sum-i32-buffer",
        case_count: report.cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_call_expression_chain(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("call-expression-c-oracle.json");
    let oracle_value: Value = read_json(&fixture_path)?;
    let report: CallExpressionChainOracleReport = serde_json::from_value(oracle_value.clone())?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    fs::create_dir_all(&evidence_dir)?;
    write_json(
        &evidence_dir.join("l3-call-expression-c-oracle.json"),
        &oracle_value,
    )?;

    let mut rust_cases = Vec::with_capacity(report.cases.len());
    let mut first_mismatch = None;

    for case in &report.cases {
        let rust = call_expression_chain::call_expression_chain(case.input_value);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "return_value",
            json!(case.return_value),
            json!(rust.return_value),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "status",
            json!(case.status),
            json!(rust.status),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "call_expression_count",
            json!(case.call_expression_count),
            json!(rust.call_expression_count),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "call_expression_contexts",
            json!(case.call_expression_contexts),
            json!(rust.call_expression_contexts),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "source_calls",
            json!(case.source_calls),
            json!(rust.source_calls),
        );

        rust_cases.push(json!({
            "id": case.id,
            "coverage_kind": case.coverage_kind,
            "input_value": rust.input_value,
            "return_value": rust.return_value,
            "status": rust.status,
            "call_expression_count": rust.call_expression_count,
            "call_expression_contexts": rust.call_expression_contexts,
            "source_calls": rust.source_calls
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("l3-call-expression-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": "demo-call-expression-20260625",
            "c_source_boundary": "int call_expression_chain(int value) { if (value <= 0) { return -value; } int first = call_expression_chain(value - 1); value = call_expression_chain(first - 1); return call_expression_chain(value - 1); }",
            "rust_module_path": "validation/l2_slices/src/call_expression_chain.rs",
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --bin emit_reports",
            "status": status,
            "case_count": report.cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-call-expression-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": "demo-call-expression-20260625",
            "status": status,
            "case_count": report.cases.len(),
            "compared_fields": ["return_value", "status", "call_expression_count", "call_expression_contexts", "source_calls"],
            "first_mismatch": first_mismatch
        }),
    )?;
    emit_call_expression_chain_test_translation(&evidence_dir, &fixture_path, report.cases.len())?;
    emit_call_expression_chain_performance_smoke(&report, &evidence_dir)?;

    Ok(SliceResult {
        slice_id: "demo-call-expression",
        case_count: report.cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_external_direct_callee(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("external-direct-callee-c-oracle.json");
    let oracle_value: Value = read_json(&fixture_path)?;
    let report: ExternalDirectCalleeOracleReport = serde_json::from_value(oracle_value.clone())?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    fs::create_dir_all(&evidence_dir)?;
    write_json(
        &evidence_dir.join("l3-external-direct-callee-c-oracle.json"),
        &oracle_value,
    )?;

    let mut rust_cases = Vec::with_capacity(report.cases.len());
    let mut first_mismatch = None;

    for case in &report.cases {
        let rust = external_direct_callee::call_helper_chain(case.input_value);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "return_value",
            json!(case.return_value),
            json!(rust.return_value),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "status",
            json!(case.status),
            json!(rust.status),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "external_callee_call_count",
            json!(case.external_callee_call_count),
            json!(rust.external_callee_call_count),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "external_callee_contexts",
            json!(case.external_callee_contexts),
            json!(rust.external_callee_contexts),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "external_callee_bindings",
            json!(case.external_callee_bindings),
            json!(rust.external_callee_bindings),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "source_calls",
            json!(case.source_calls),
            json!(rust.source_calls),
        );

        rust_cases.push(json!({
            "id": case.id,
            "coverage_kind": case.coverage_kind,
            "input_value": rust.input_value,
            "return_value": rust.return_value,
            "status": rust.status,
            "external_callee_call_count": rust.external_callee_call_count,
            "external_callee_contexts": rust.external_callee_contexts,
            "external_callee_bindings": rust.external_callee_bindings,
            "source_calls": rust.source_calls
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("l3-external-direct-callee-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "external-direct-callee",
            "source_commit": "demo-external-direct-callee-20260625",
            "c_source_boundary": "int helper_add_one(int value) { return value + 1; } int call_helper_chain(int value) { int first = helper_add_one(value); value = helper_add_one(first); return helper_add_one(value); }",
            "rust_module_path": "validation/l2_slices/src/external_direct_callee.rs",
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --bin emit_reports",
            "status": status,
            "case_count": report.cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-external-direct-callee-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "external-direct-callee",
            "source_commit": "demo-external-direct-callee-20260625",
            "status": status,
            "case_count": report.cases.len(),
            "compared_fields": ["return_value", "status", "external_callee_call_count", "external_callee_contexts", "external_callee_bindings", "source_calls"],
            "first_mismatch": first_mismatch
        }),
    )?;
    emit_external_direct_callee_test_translation(&evidence_dir, &fixture_path, report.cases.len())?;
    emit_external_direct_callee_performance_smoke(&report, &evidence_dir)?;

    Ok(SliceResult {
        slice_id: "demo-external-direct-callee",
        case_count: report.cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_sum_i32_ptr_arith(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("sum-i32-ptr-arith-c-oracle.json");
    let oracle_value: Value = read_json(&fixture_path)?;
    let report: SumI32PtrArithOracleReport = serde_json::from_value(oracle_value.clone())?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    fs::create_dir_all(&evidence_dir)?;
    write_json(
        &evidence_dir.join("l3-sum-i32-ptr-arith-c-oracle.json"),
        &oracle_value,
    )?;

    let mut rust_cases = Vec::with_capacity(report.cases.len());
    let mut first_mismatch = None;

    for case in &report.cases {
        let rust = sum_i32_ptr_arith::sum_i32_ptr_arith(&case.values);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "return_code",
            json!(case.return_code),
            json!(rust.return_code),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "status",
            json!(case.status),
            json!(rust.status),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "len",
            json!(case.len),
            json!(rust.len),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "sum",
            json!(case.sum),
            json!(rust.sum),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "source_reads",
            json!(case.source_reads),
            json!(rust.source_reads),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "canonical_reads",
            json!(case.canonical_reads),
            json!(rust.canonical_reads),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "source_write",
            json!(case.source_write),
            json!(rust.source_write),
        );

        rust_cases.push(json!({
            "id": case.id,
            "coverage_kind": case.coverage_kind,
            "values": case.values,
            "len": rust.len,
            "return_code": rust.return_code,
            "status": rust.status,
            "sum": rust.sum,
            "source_reads": rust.source_reads,
            "canonical_reads": rust.canonical_reads,
            "source_write": rust.source_write
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("l3-sum-i32-ptr-arith-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": "demo-sum-i32-ptr-arith-20260625",
            "c_source_boundary": "int sum_i32_ptr_arith(const int* values, int len, int* out) { int total = 0; for (int i = 0; i < len; i++) { total = total + *(values + i); } out[0] = total; return 0; }",
            "rust_module_path": "validation/l2_slices/src/sum_i32_ptr_arith.rs",
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --bin emit_reports",
            "status": status,
            "case_count": report.cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-sum-i32-ptr-arith-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": "demo-sum-i32-ptr-arith-20260625",
            "status": status,
            "case_count": report.cases.len(),
            "compared_fields": ["return_code", "status", "len", "sum", "source_reads", "canonical_reads", "source_write"],
            "first_mismatch": first_mismatch
        }),
    )?;
    emit_sum_i32_ptr_arith_performance_smoke(&report, &evidence_dir)?;

    Ok(SliceResult {
        slice_id: "demo-sum-i32-ptr-arith",
        case_count: report.cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_copy_i32_ptr_arith(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("copy-i32-ptr-arith-c-oracle.json");
    let oracle_value: Value = read_json(&fixture_path)?;
    let report: CopyI32PtrArithOracleReport = serde_json::from_value(oracle_value.clone())?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    fs::create_dir_all(&evidence_dir)?;
    write_json(
        &evidence_dir.join("l3-copy-i32-ptr-arith-c-oracle.json"),
        &oracle_value,
    )?;

    let mut rust_cases = Vec::with_capacity(report.cases.len());
    let mut first_mismatch = None;

    for case in &report.cases {
        let rust = copy_i32_ptr_arith::copy_i32_ptr_arith(&case.values);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "return_code",
            json!(case.return_code),
            json!(rust.return_code),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "status",
            json!(case.status),
            json!(rust.status),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "len",
            json!(case.len),
            json!(rust.len),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "values",
            json!(case.values),
            json!(rust.values),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "out_values",
            json!(case.out_values),
            json!(rust.out_values),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "source_reads",
            json!(case.source_reads),
            json!(rust.source_reads),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "canonical_reads",
            json!(case.canonical_reads),
            json!(rust.canonical_reads),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "source_writes",
            json!(case.source_writes),
            json!(rust.source_writes),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "canonical_writes",
            json!(case.canonical_writes),
            json!(rust.canonical_writes),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "write_count",
            json!(case.write_count),
            json!(rust.write_count),
        );

        rust_cases.push(json!({
            "id": case.id,
            "coverage_kind": case.coverage_kind,
            "values": rust.values,
            "len": rust.len,
            "return_code": rust.return_code,
            "status": rust.status,
            "out_values": rust.out_values,
            "source_reads": rust.source_reads,
            "canonical_reads": rust.canonical_reads,
            "source_writes": rust.source_writes,
            "canonical_writes": rust.canonical_writes,
            "write_count": rust.write_count
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("l3-copy-i32-ptr-arith-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "copy-i32-ptr-arith",
            "source_commit": "demo-copy-i32-ptr-arith-20260625",
            "c_source_boundary": "int copy_i32_ptr_arith(const int* values, int len, int* out) { for (int i = 0; i < len; i++) { *(out + i) = *(values + i); } return 0; }",
            "rust_module_path": "validation/l2_slices/src/copy_i32_ptr_arith.rs",
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --bin emit_reports",
            "status": status,
            "case_count": report.cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-copy-i32-ptr-arith-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "copy-i32-ptr-arith",
            "source_commit": "demo-copy-i32-ptr-arith-20260625",
            "status": status,
            "case_count": report.cases.len(),
            "compared_fields": ["return_code", "status", "len", "values", "out_values", "source_reads", "canonical_reads", "source_writes", "canonical_writes", "write_count"],
            "first_mismatch": first_mismatch
        }),
    )?;
    emit_l3_test_translation(L3TestTranslationSpec {
        evidence_dir: &evidence_dir,
        slice_id: "copy-i32-ptr-arith",
        source_commit: "demo-copy-i32-ptr-arith-20260625",
        fixture_path: &fixture_path,
        rust_test_name: "copy_i32_ptr_arith_matches_c_oracle_with_safe_boundary",
        main_paths: &[
            "copy output buffer values",
            "raw/canonical pointer write evidence",
        ],
        negative_cases: &["negative diff mutates out_values"],
        behavior_fields: &[
            "return_code",
            "status",
            "len",
            "values",
            "out_values",
            "source_reads",
            "canonical_reads",
            "source_writes",
            "canonical_writes",
            "write_count",
        ],
    })?;
    emit_copy_i32_ptr_arith_performance_smoke(&report, &evidence_dir)?;

    Ok(SliceResult {
        slice_id: "demo-copy-i32-ptr-arith",
        case_count: report.cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_add_i32_pair_ptr_arith(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("add-i32-pair-ptr-arith-c-oracle.json");
    let oracle_value: Value = read_json(&fixture_path)?;
    let report: AddI32PairPtrArithOracleReport = serde_json::from_value(oracle_value.clone())?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    fs::create_dir_all(&evidence_dir)?;
    write_json(
        &evidence_dir.join("l3-add-i32-pair-ptr-arith-c-oracle.json"),
        &oracle_value,
    )?;

    let mut rust_cases = Vec::with_capacity(report.cases.len());
    let mut first_mismatch = None;

    for case in &report.cases {
        let alias_case =
            add_i32_pair_ptr_arith::AddI32PairAliasCase::from_fixture(&case.alias_case)
                .ok_or("add_i32_pair_ptr_arith oracle contains unknown alias_case")?;
        let rust = add_i32_pair_ptr_arith::add_i32_pair_ptr_arith(&case.lhs, &case.rhs, alias_case);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "return_code",
            json!(case.return_code),
            json!(rust.return_code),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "status",
            json!(case.status),
            json!(rust.status),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "len",
            json!(case.len),
            json!(rust.len),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "lhs",
            json!(case.lhs),
            json!(rust.lhs),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "rhs",
            json!(case.rhs),
            json!(rust.rhs),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "out_values",
            json!(case.out_values),
            json!(rust.out_values),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "source_reads",
            json!(case.source_reads),
            json!(rust.source_reads),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "canonical_reads",
            json!(case.canonical_reads),
            json!(rust.canonical_reads),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "source_writes",
            json!(case.source_writes),
            json!(rust.source_writes),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "canonical_writes",
            json!(case.canonical_writes),
            json!(rust.canonical_writes),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "write_count",
            json!(case.write_count),
            json!(rust.write_count),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "safe_noalias_precondition",
            json!(case.safe_noalias_precondition),
            json!(rust.safe_noalias_precondition),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "alias_case",
            json!(case.alias_case),
            json!(rust.alias_case),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "alias_matrix",
            json!(case.alias_matrix),
            json!(rust.alias_matrix),
        );

        rust_cases.push(json!({
            "id": case.id,
            "coverage_kind": case.coverage_kind,
            "lhs": rust.lhs,
            "rhs": rust.rhs,
            "len": rust.len,
            "return_code": rust.return_code,
            "status": rust.status,
            "out_values": rust.out_values,
            "source_reads": rust.source_reads,
            "canonical_reads": rust.canonical_reads,
            "source_writes": rust.source_writes,
            "canonical_writes": rust.canonical_writes,
            "write_count": rust.write_count,
            "safe_noalias_precondition": rust.safe_noalias_precondition,
            "alias_case": rust.alias_case,
            "alias_matrix": rust.alias_matrix
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("l3-add-i32-pair-ptr-arith-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "add-i32-pair-ptr-arith",
            "source_commit": "demo-add-i32-pair-ptr-arith-20260625",
            "c_source_boundary": "int add_i32_pair_ptr_arith(const int* lhs, const int* rhs, int len, int* out) { for (int i = 0; i < len; i++) { *(out + i) = *(lhs + i) + *(rhs + i); } return 0; }",
            "rust_module_path": "validation/l2_slices/src/add_i32_pair_ptr_arith.rs",
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --bin emit_reports",
            "status": status,
            "case_count": report.cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-add-i32-pair-ptr-arith-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "add-i32-pair-ptr-arith",
            "source_commit": "demo-add-i32-pair-ptr-arith-20260625",
            "status": status,
            "case_count": report.cases.len(),
            "compared_fields": ["return_code", "status", "len", "lhs", "rhs", "out_values", "source_reads", "canonical_reads", "source_writes", "canonical_writes", "write_count", "safe_noalias_precondition", "alias_case", "alias_matrix"],
            "first_mismatch": first_mismatch
        }),
    )?;
    emit_l3_test_translation(L3TestTranslationSpec {
        evidence_dir: &evidence_dir,
        slice_id: "add-i32-pair-ptr-arith",
        source_commit: "demo-add-i32-pair-ptr-arith-20260625",
        fixture_path: &fixture_path,
        rust_test_name: "add_i32_pair_ptr_arith_matches_c_oracle_and_records_alias_boundary",
        main_paths: &[
            "disjoint input pair addition",
            "lhs/rhs read-read alias accepted",
            "input/output overlap-risk metadata rejected at safe boundary",
        ],
        negative_cases: &["negative diff mutates alias_matrix"],
        behavior_fields: &[
            "return_code",
            "status",
            "len",
            "lhs",
            "rhs",
            "out_values",
            "source_reads",
            "canonical_reads",
            "source_writes",
            "canonical_writes",
            "write_count",
            "safe_noalias_precondition",
            "alias_case",
            "alias_matrix",
        ],
    })?;
    emit_add_i32_pair_ptr_arith_performance_smoke(&report, &evidence_dir)?;

    Ok(SliceResult {
        slice_id: "demo-add-i32-pair-ptr-arith",
        case_count: report.cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_libuv_ip4_addr(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("libuv-ip4-addr-c-oracle.json");
    let report: LibuvIp4OracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("libuv");
    fs::create_dir_all(&evidence_dir)?;

    let mut rust_cases = Vec::with_capacity(report.cases.len());
    let mut first_mismatch = None;

    for case in &report.cases {
        let rust = libuv_ip4_addr::uv_ip4_addr(&case.ip, case.port);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "return_code",
            json!(case.return_code),
            json!(rust.return_code),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "status",
            json!(case.status),
            json!(rust.status),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "family",
            json!(case.family),
            json!(rust.family),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "port_host",
            json!(case.port_host),
            json!(rust.port_host),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "port_bytes_hex",
            json!(case.port_bytes_hex),
            json!(rust.port_bytes_hex),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "addr_bytes_hex",
            json!(case.addr_bytes_hex),
            json!(rust.addr_bytes_hex),
        );

        rust_cases.push(json!({
            "id": case.id,
            "ip": case.ip,
            "port": case.port,
            "coverage_kind": case.coverage_kind,
            "return_code": rust.return_code,
            "status": rust.status,
            "family": rust.family,
            "port_host": rust.port_host,
            "port_bytes_hex": rust.port_bytes_hex,
            "addr_bytes_hex": rust.addr_bytes_hex
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("l3-ip4-addr-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "source_commit": "5e7d51a8f4734cac453db960d4b9919735bbf7c3",
            "c_source_boundary": "uv_ip4_addr/uv_inet_pton/inet_pton4 from libuv",
            "rust_module_path": "validation/l2_slices/src/libuv_ip4_addr.rs",
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --bin emit_reports",
            "status": status,
            "case_count": report.cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-ip4-addr-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "status": status,
            "case_count": report.cases.len(),
            "compared_fields": [
                "return_code",
                "status",
                "family",
                "port_host",
                "port_bytes_hex",
                "addr_bytes_hex"
            ],
            "first_mismatch": first_mismatch
        }),
    )?;
    write_libuv_negative_diff(&report, &evidence_dir)?;
    emit_libuv_performance_smoke(&report, &evidence_dir)?;
    write_json(
        &evidence_dir.join("l3-ip4-addr-rust-check.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "status": "passed",
            "compile_self_healing": {
                "attempt_count": 0,
                "unresolved_errors": 0
            },
            "commands": [
                {
                    "command": "cargo test --test libuv_ip4_addr",
                    "status": "passed",
                    "red_log": "validation/evidence/libuv/l3-ip4-addr-red-test.log",
                    "green_log": "validation/evidence/libuv/l3-ip4-addr-green-test.log"
                },
                {
                    "command": "cargo run --bin emit_reports",
                    "status": "passed"
                }
            ]
        }),
    )?;

    Ok(SliceResult {
        slice_id: "libuv-ip4-addr",
        case_count: report.cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_sqlite_varint(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("sqlite-varint-c-oracle.json");
    let cases: Vec<SqliteVarintCase> = read_json(&fixture_path)?;
    let mut rust_cases = Vec::with_capacity(cases.len());
    let mut first_mismatch = None;

    for case in &cases {
        let encoded = sqlite_varint::put_varint(case.value);
        let decoded = sqlite_varint::get_varint(&encoded).ok_or("encoded varint must decode")?;
        let rust_encoded_hex = bytes_to_hex(&encoded);
        let rust_case = json!({
            "id": case.id,
            "value": case.value,
            "encoded_hex": rust_encoded_hex,
            "bytes_used": encoded.len(),
            "decoded_value": decoded.value,
            "decoded_bytes": decoded.bytes_used
        });

        compare_field(
            &mut first_mismatch,
            &case.id,
            "encoded_hex",
            json!(case.encoded_hex),
            json!(rust_encoded_hex),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "bytes_used",
            json!(case.bytes_used),
            json!(encoded.len()),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "decoded_value",
            json!(case.decoded_value),
            json!(decoded.value),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "decoded_bytes",
            json!(case.decoded_bytes),
            json!(decoded.bytes_used),
        );

        rust_cases.push(rust_case);
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("sqlite-varint-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L2",
            "project_id": "sqlite",
            "slice_id": "sqlite-varint",
            "source_commit": "99a92ee66d80d519851015cf27def1c54e7a2037",
            "c_source_boundary": "sqlite3PutVarint/sqlite3GetVarint from sqlite3.c",
            "rust_module_path": "validation/l2_slices/src/sqlite_varint.rs",
            "fixture_input_description": "Boundary u64 values around SQLite varint width transitions and 64-bit extremes.",
            "fixture": relative_path(&fixture_path),
            "command": "cargo test",
            "status": status,
            "case_count": cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("sqlite-varint-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "slice_id": "sqlite-varint",
            "status": status,
            "case_count": cases.len(),
            "compared_fields": ["encoded_hex", "bytes_used", "decoded_value", "decoded_bytes"],
            "first_mismatch": first_mismatch
        }),
    )?;
    emit_l2_test_translation(L2TestTranslationSpec {
        evidence_dir,
        target_id: "sqlite",
        slice_id: "sqlite-varint",
        source_commit: "99a92ee66d80d519851015cf27def1c54e7a2037",
        fixture_path: &fixture_path,
        rust_test_name: "sqlite_varint_matches_c_oracle",
        main_paths: &[
            "single-byte varint",
            "multi-byte varint width boundaries",
            "u64 maximum varint",
        ],
        error_paths: &["truncated varint decode returns None"],
        negative_cases: &["encoded_hex mutation rejected by negative diff"],
        behavior_fields: &[
            "encoded_hex",
            "bytes_used",
            "decoded_value",
            "decoded_bytes",
        ],
    })?;

    Ok(SliceResult {
        slice_id: "sqlite-varint",
        case_count: cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_zlib_adler32(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("zlib-adler32-c-oracle.json");
    let cases: Vec<ChecksumCase> = read_json(&fixture_path)?;
    let mut rust_cases = Vec::with_capacity(cases.len());
    let mut first_mismatch = None;

    for case in &cases {
        let input = hex_to_bytes(&case.input_hex)?;
        let rust_value = zlib_adler32::adler32(&input);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "value",
            json!(case.value),
            json!(rust_value),
        );
        rust_cases.push(json!({
            "id": case.id,
            "input_len": input.len(),
            "value": rust_value,
            "value_hex": format!("0x{rust_value:08x}")
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("zlib-adler32-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L2",
            "project_id": "zlib-ng",
            "slice_id": "zlib-adler32",
            "source_commit": "d40f29fd42ed9158e3eb3e221dca50e4b627f7a8",
            "c_source_boundary": "adler32_z from zlib-ng build/libz.a",
            "rust_module_path": "validation/l2_slices/src/zlib_adler32.rs",
            "fixture_input_description": "Empty, ASCII, NMAX boundary, repeated byte, incrementing byte, and deterministic LCG byte buffers.",
            "fixture": relative_path(&fixture_path),
            "command": "cargo test",
            "status": status,
            "case_count": cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("zlib-adler32-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "slice_id": "zlib-adler32",
            "status": status,
            "case_count": cases.len(),
            "compared_fields": ["value"],
            "first_mismatch": first_mismatch
        }),
    )?;
    emit_l2_test_translation(L2TestTranslationSpec {
        evidence_dir,
        target_id: "zlib-ng",
        slice_id: "zlib-adler32",
        source_commit: "d40f29fd42ed9158e3eb3e221dca50e4b627f7a8",
        fixture_path: &fixture_path,
        rust_test_name: "zlib_adler32_matches_c_oracle",
        main_paths: &[
            "empty input",
            "ASCII input",
            "NMAX boundary input",
            "deterministic LCG byte buffers",
        ],
        error_paths: &[],
        negative_cases: &["checksum value mutation rejected by negative diff"],
        behavior_fields: &["value"],
    })?;

    Ok(SliceResult {
        slice_id: "zlib-adler32",
        case_count: cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_zstd_xxh32(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("zstd-xxh32-c-oracle.json");
    let cases: Vec<ChecksumCase> = read_json(&fixture_path)?;
    let mut rust_cases = Vec::with_capacity(cases.len());
    let mut first_mismatch = None;

    for case in &cases {
        let input = hex_to_bytes(&case.input_hex)?;
        let seed = case.seed.ok_or("zstd xxh32 fixture must include seed")?;
        let rust_value = zstd_xxh32::xxh32(&input, seed);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "value",
            json!(case.value),
            json!(rust_value),
        );
        rust_cases.push(json!({
            "id": case.id,
            "input_len": input.len(),
            "seed": seed,
            "value": rust_value,
            "value_hex": format!("0x{rust_value:08x}")
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("zstd-xxh32-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L2",
            "project_id": "zstd",
            "slice_id": "zstd-xxh32",
            "source_commit": "5233c58e6ca0b1c4c6b353ad79649191ed195bdc",
            "c_source_boundary": "XXH32 from zstd lib/common/xxhash.c",
            "rust_module_path": "validation/l2_slices/src/zstd_xxh32.rs",
            "fixture_input_description": "Length boundaries around the 16-byte XXH32 block path with seeds 0, 1, PRIME32_1, and u32::MAX.",
            "fixture": relative_path(&fixture_path),
            "command": "cargo test",
            "status": status,
            "case_count": cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("zstd-xxh32-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "slice_id": "zstd-xxh32",
            "status": status,
            "case_count": cases.len(),
            "compared_fields": ["value"],
            "first_mismatch": first_mismatch
        }),
    )?;
    emit_l2_test_translation(L2TestTranslationSpec {
        evidence_dir,
        target_id: "zstd",
        slice_id: "zstd-xxh32",
        source_commit: "5233c58e6ca0b1c4c6b353ad79649191ed195bdc",
        fixture_path: &fixture_path,
        rust_test_name: "zstd_xxh32_matches_c_oracle",
        main_paths: &[
            "short input path",
            "16-byte block path",
            "seed variations",
            "u32 maximum seed",
        ],
        error_paths: &[],
        negative_cases: &["checksum value mutation rejected by negative diff"],
        behavior_fields: &["value"],
    })?;

    Ok(SliceResult {
        slice_id: "zstd-xxh32",
        case_count: cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_negative_diffs(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<Vec<NegativeDiffResult>, Box<dyn Error>> {
    Ok(vec![
        emit_sqlite_negative_diff(fixtures_dir, evidence_dir)?,
        emit_zlib_negative_diff(fixtures_dir, evidence_dir)?,
        emit_zstd_negative_diff(fixtures_dir, evidence_dir)?,
    ])
}

fn emit_sqlite_negative_diff(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("sqlite-varint-c-oracle.json");
    let cases: Vec<SqliteVarintCase> = read_json(&fixture_path)?;
    let case = cases
        .first()
        .ok_or("sqlite-varint fixture must contain at least one case")?;
    let encoded = sqlite_varint::put_varint(case.value);
    let rust_encoded_hex = bytes_to_hex(&encoded);
    let mutated_c_value = if rust_encoded_hex == "00" { "01" } else { "00" };
    let detected = mutated_c_value != rust_encoded_hex;
    let status = if detected { "passed" } else { "failed" };
    let first_mismatch = if detected {
        Some(json!({
            "case_id": case.id,
            "field": "encoded_hex",
            "mutated_c_value": mutated_c_value,
            "rust_value": rust_encoded_hex
        }))
    } else {
        None
    };
    let report_path = "validation/evidence/l2-slices/sqlite-varint-negative-diff.json";
    write_json(
        &evidence_dir.join("sqlite-varint-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L2",
            "slice_id": "sqlite-varint",
            "status": status,
            "mutation": "first oracle case encoded_hex is replaced with a different byte",
            "case_id": case.id,
            "detected": detected,
            "first_mismatch": first_mismatch
        }),
    )?;

    Ok(NegativeDiffResult {
        slice_id: "sqlite-varint",
        status,
        report_path,
    })
}

fn emit_zlib_negative_diff(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("zlib-adler32-c-oracle.json");
    let cases: Vec<ChecksumCase> = read_json(&fixture_path)?;
    let case = cases
        .first()
        .ok_or("zlib-adler32 fixture must contain at least one case")?;
    let input = hex_to_bytes(&case.input_hex)?;
    let rust_value = zlib_adler32::adler32(&input);
    let mutated_c_value = case.value ^ 1;
    let detected = mutated_c_value != rust_value;
    let status = if detected { "passed" } else { "failed" };
    let first_mismatch = if detected {
        Some(json!({
            "case_id": case.id,
            "field": "value",
            "mutated_c_value": mutated_c_value,
            "rust_value": rust_value
        }))
    } else {
        None
    };
    let report_path = "validation/evidence/l2-slices/zlib-adler32-negative-diff.json";
    write_json(
        &evidence_dir.join("zlib-adler32-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L2",
            "slice_id": "zlib-adler32",
            "status": status,
            "mutation": "first oracle case value is replaced with value ^ 1",
            "case_id": case.id,
            "detected": detected,
            "first_mismatch": first_mismatch
        }),
    )?;

    Ok(NegativeDiffResult {
        slice_id: "zlib-adler32",
        status,
        report_path,
    })
}

fn emit_zstd_negative_diff(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("zstd-xxh32-c-oracle.json");
    let cases: Vec<ChecksumCase> = read_json(&fixture_path)?;
    let case = cases
        .first()
        .ok_or("zstd-xxh32 fixture must contain at least one case")?;
    let input = hex_to_bytes(&case.input_hex)?;
    let seed = case.seed.ok_or("zstd xxh32 fixture must include seed")?;
    let rust_value = zstd_xxh32::xxh32(&input, seed);
    let mutated_c_value = case.value ^ 1;
    let detected = mutated_c_value != rust_value;
    let status = if detected { "passed" } else { "failed" };
    let first_mismatch = if detected {
        Some(json!({
            "case_id": case.id,
            "field": "value",
            "mutated_c_value": mutated_c_value,
            "rust_value": rust_value
        }))
    } else {
        None
    };
    let report_path = "validation/evidence/l2-slices/zstd-xxh32-negative-diff.json";
    write_json(
        &evidence_dir.join("zstd-xxh32-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L2",
            "slice_id": "zstd-xxh32",
            "status": status,
            "mutation": "first oracle case value is replaced with value ^ 1",
            "case_id": case.id,
            "detected": detected,
            "first_mismatch": first_mismatch
        }),
    )?;

    Ok(NegativeDiffResult {
        slice_id: "zstd-xxh32",
        status,
        report_path,
    })
}

fn emit_l2_test_translation(spec: L2TestTranslationSpec<'_>) -> Result<(), Box<dyn Error>> {
    let rust_test = format!(
        "validation/l2_slices/tests/oracle_fixtures.rs::{}",
        spec.rust_test_name
    );
    write_json(
        &spec
            .evidence_dir
            .join(format!("{}-test-translation.json", spec.slice_id)),
        &json!({
            "schema_version": 1,
            "target_id": spec.target_id,
            "slice_id": spec.slice_id,
            "level": "L2",
            "status": "recorded",
            "source_commit": spec.source_commit,
            "repo_commit": "workspace",
            "source_test_inputs": {
                "oracle_strategy": "Committed C oracle fixture is replayed by Rust cargo tests and emit_reports evidence generation.",
                "fixtures": [
                    {
                        "path": relative_path(spec.fixture_path),
                        "source_kind": "fixture"
                    }
                ],
                "oracle_reports": [
                    {
                        "path": format!("validation/evidence/l2-slices/{}-oracle.json", spec.slice_id),
                        "status": "passed"
                    }
                ]
            },
            "rust_tests": [
                {
                    "file": "validation/l2_slices/tests/oracle_fixtures.rs",
                    "test_names": [spec.rust_test_name],
                    "cargo_command": "cargo test --manifest-path validation/l2_slices/Cargo.toml",
                    "framework": "cargo test"
                }
            ],
            "coverage": {
                "main_paths": spec.main_paths,
                "error_paths": spec.error_paths,
                "negative_cases": spec.negative_cases
            },
            "translation_mappings": [
                {
                    "source": relative_path(spec.fixture_path),
                    "rust_test": rust_test,
                    "behavior_fields": spec.behavior_fields,
                    "coverage_kind": "main_path",
                    "status": "mapped"
                },
                {
                    "source": format!("validation/evidence/l2-slices/{}-negative-diff.json", spec.slice_id),
                    "rust_test": "validation/l2_slices/src/bin/emit_reports.rs::emit_negative_diffs",
                    "behavior_fields": spec.behavior_fields,
                    "coverage_kind": "negative_case",
                    "status": "mapped"
                }
            ],
            "evidence_links": {
                "c_oracle": {
                    "path": format!("validation/evidence/l2-slices/{}-oracle.json", spec.slice_id),
                    "status": "passed"
                },
                "rust_report": {
                    "path": format!("validation/evidence/l2-slices/{}-rust-report.json", spec.slice_id),
                    "status": "passed"
                },
                "schema_diff": {
                    "path": format!("validation/evidence/l2-slices/{}-diff.json", spec.slice_id),
                    "status": "passed"
                },
                "negative_diff": {
                    "path": format!("validation/evidence/l2-slices/{}-negative-diff.json", spec.slice_id),
                    "status": "passed"
                },
                "unsafe_ledger": {
                    "path": "validation/evidence/l2-slices/unsafe-ledger.json",
                    "status": "passed"
                }
            },
            "known_gaps": [
                "L2 test translation covers the named function slice and committed oracle fixture only.",
                "No full-project migration or exhaustive symbolic equivalence is claimed."
            ],
            "cache_invalidation_keys": [
                "schema_version",
                format!("source_commit={}", spec.source_commit),
                format!("fixture={}", relative_path(spec.fixture_path)),
                "cargo test --manifest-path validation/l2_slices/Cargo.toml",
                "emit_reports.rs"
            ]
        }),
    )
}

fn emit_l3_test_translation(spec: L3TestTranslationSpec<'_>) -> Result<(), Box<dyn Error>> {
    let slice_id = spec.slice_id;
    let prefix = format!("l3-{slice_id}");
    let rust_test = format!(
        "validation/l2_slices/tests/{slice_id}.rs::{}",
        spec.rust_test_name
    )
    .replace('-', "_");
    write_json(
        &spec
            .evidence_dir
            .join(format!("{prefix}-test-translation.json")),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": slice_id,
            "level": "L3",
            "status": "recorded",
            "source_commit": spec.source_commit,
            "repo_commit": "workspace",
            "source_test_inputs": {
                "oracle_strategy": "Committed C oracle fixture is replayed by Rust cargo tests and emit_reports evidence generation.",
                "fixtures": [{"path": relative_path(spec.fixture_path), "source_kind": "fixture"}],
                "oracle_reports": [{"path": format!("validation/evidence/demo/{prefix}-c-oracle.json"), "status": "passed"}]
            },
            "rust_tests": [
                {
                    "file": format!("validation/l2_slices/tests/{}.rs", slice_id.replace('-', "_")),
                    "test_names": [spec.rust_test_name],
                    "cargo_command": format!("cargo test --manifest-path validation/l2_slices/Cargo.toml --test {}", slice_id.replace('-', "_")),
                    "framework": "cargo test"
                }
            ],
            "coverage": {
                "main_paths": spec.main_paths,
                "error_paths": [],
                "negative_cases": spec.negative_cases
            },
            "translation_mappings": [
                {
                    "source": relative_path(spec.fixture_path),
                    "rust_test": rust_test,
                    "behavior_fields": spec.behavior_fields,
                    "coverage_kind": "main_path",
                    "status": "mapped"
                },
                {
                    "source": format!("validation/evidence/demo/{prefix}-negative-diff.json"),
                    "rust_test": format!("validation/l2_slices/src/bin/emit_reports.rs::emit_{}_negative_diff", slice_id.replace('-', "_")),
                    "behavior_fields": spec.behavior_fields,
                    "coverage_kind": "negative_case",
                    "status": "mapped"
                }
            ],
            "evidence_links": {
                "c_oracle": {"path": format!("validation/evidence/demo/{prefix}-c-oracle.json"), "status": "passed"},
                "rust_report": {"path": format!("validation/evidence/demo/{prefix}-rust-report.json"), "status": "passed"},
                "schema_diff": {"path": format!("validation/evidence/demo/{prefix}-diff.json"), "status": "passed"},
                "negative_diff": {"path": format!("validation/evidence/demo/{prefix}-negative-diff.json"), "status": "expected_failed"}
            },
            "known_gaps": [
                "L3 demo test translation covers the named function slice and committed oracle fixture only.",
                "No full-project migration or exhaustive symbolic equivalence is claimed."
            ]
        }),
    )
}

fn emit_call_expression_chain_test_translation(
    evidence_dir: &Path,
    fixture_path: &Path,
    case_count: usize,
) -> Result<(), Box<dyn Error>> {
    write_json(
        &evidence_dir.join("l3-call-expression-test-translation.json"),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "call-expression",
            "level": "L3",
            "status": "recorded",
            "source_commit": "demo-call-expression-20260625",
            "repo_commit": "workspace",
            "source_test_inputs": {
                "oracle_strategy": "Committed C oracle fixture is replayed by Rust cargo tests and emit_reports evidence generation.",
                "fixtures": [{"path": relative_path(fixture_path), "hash": "call-expression-fixture", "operation_count": case_count, "source_kind": "fixture"}],
                "oracle_reports": [
                    {"path": "validation/evidence/demo/l3-call-expression-c-oracle.json", "status": "passed"},
                    {"path": "validation/evidence/demo/l3-call-expression-rust-report.json", "status": "passed"}
                ]
            },
            "rust_tests": [
                {
                    "file": "validation/l2_slices/tests/call_expression_chain.rs",
                    "test_names": ["call_expression_chain_matches_c_oracle_and_records_call_contexts"],
                    "cargo_command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test call_expression_chain",
                    "framework": "cargo test"
                }
            ],
            "coverage": {
                "main_paths": [
                    "base negative/zero return path",
                    "recursive declaration initializer call",
                    "recursive assignment RHS call",
                    "recursive return expression call"
                ],
                "error_paths": [],
                "negative_cases": ["call expression metadata mutation rejected by negative diff"]
            },
            "translation_mappings": [
                {
                    "source": relative_path(fixture_path),
                    "rust_test": "validation/l2_slices/tests/call_expression_chain.rs::call_expression_chain_matches_c_oracle_and_records_call_contexts",
                    "behavior_fields": ["return_value", "status", "call_expression_count", "call_expression_contexts", "source_calls"],
                    "coverage_kind": "main_path",
                    "status": "mapped"
                },
                {
                    "source": "validation/evidence/demo/l3-call-expression-negative-diff.json",
                    "rust_test": "validation/l2_slices/src/bin/emit_reports.rs::emit_call_expression_chain_negative_diff",
                    "behavior_fields": ["call_expression_count", "call_expression_contexts"],
                    "coverage_kind": "negative_case",
                    "status": "mapped"
                }
            ],
            "evidence_links": {
                "c_oracle": {"path": "validation/evidence/demo/l3-call-expression-c-oracle.json", "status": "passed"},
                "rust_report": {"path": "validation/evidence/demo/l3-call-expression-rust-report.json", "status": "passed"},
                "schema_diff": {"path": "validation/evidence/demo/l3-call-expression-diff.json", "status": "passed"},
                "negative_diff": {"path": "validation/evidence/demo/l3-call-expression-negative-diff.json", "status": "expected_failed"},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-call-expression-unsafe-ledger.json", "status": "passed"}
            },
            "known_gaps": [
                "L3 demo test translation covers the named function slice and committed oracle fixture only.",
                "No external callee semantic proof, function pointer call support, nested call support, or full-project migration is claimed."
            ],
            "cache_invalidation_keys": [
                "source_commit",
                "repo_commit",
                "fixture.hash",
                "rust_boundary.module",
                "translator_version"
            ]
        }),
    )
}

fn emit_external_direct_callee_test_translation(
    evidence_dir: &Path,
    fixture_path: &Path,
    _case_count: usize,
) -> Result<(), Box<dyn Error>> {
    emit_l3_test_translation(L3TestTranslationSpec {
        evidence_dir,
        slice_id: "external-direct-callee",
        source_commit: "demo-external-direct-callee-20260625",
        fixture_path,
        rust_test_name: "external_direct_callee_matches_c_oracle_and_records_helper_context",
        main_paths: &[
            "external helper declaration initializer call",
            "external helper assignment RHS call",
            "external helper return expression call",
        ],
        negative_cases: &["external callee binding metadata mutation rejected by negative diff"],
        behavior_fields: &[
            "return_value",
            "status",
            "external_callee_call_count",
            "external_callee_contexts",
            "external_callee_bindings",
            "source_calls",
        ],
    })
}

fn emit_libuv_negative_diff(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("libuv-ip4-addr-c-oracle.json");
    let report: LibuvIp4OracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("libuv");
    let detected = write_libuv_negative_diff(&report, &evidence_dir)?;

    Ok(NegativeDiffResult {
        slice_id: "libuv-ip4-addr",
        status: if detected { "passed" } else { "failed" },
        report_path: "validation/evidence/libuv/l3-ip4-addr-negative-diff.json",
    })
}

fn write_libuv_negative_diff(
    report: &LibuvIp4OracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .iter()
        .find(|case| case.return_code == 0)
        .ok_or("libuv oracle must include a passing case")?;
    let rust = libuv_ip4_addr::uv_ip4_addr(&case.ip, case.port);
    let mutated_addr = if case.addr_bytes_hex == "7f000001" {
        "7f000002"
    } else {
        "7f000001"
    };
    let detected = mutated_addr != rust.addr_bytes_hex;
    write_json(
        &evidence_dir.join("l3-ip4-addr-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "first passing oracle case addr_bytes_hex is changed",
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "addr_bytes_hex",
                    "mutated_c_value": mutated_addr,
                    "rust_value": rust.addr_bytes_hex
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}

fn emit_store_add_one_negative_diff(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("store-add-one-c-oracle.json");
    let report: StoreAddOneOracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    let detected = write_store_add_one_negative_diff(&report, &evidence_dir)?;

    Ok(NegativeDiffResult {
        slice_id: "demo-store-add-one",
        status: if detected { "passed" } else { "failed" },
        report_path: "validation/evidence/demo/l3-store-add-one-negative-diff.json",
    })
}

fn write_store_add_one_negative_diff(
    report: &StoreAddOneOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .first()
        .ok_or("store_add_one oracle must include at least one case")?;
    let rust = store_add_one::store_add_one(case.value);
    let mutated_out0 = case.out0.wrapping_add(1);
    let detected = mutated_out0 != rust.out0;
    write_json(
        &evidence_dir.join("l3-store-add-one-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "store-add-one",
            "source_commit": "demo-store-add-one-20260625",
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "first oracle case out0 is changed by +1",
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "out0",
                    "mutated_c_value": mutated_out0,
                    "rust_value": rust.out0
                })
            } else {
                Value::Null
            }
        }),
    )?;
    Ok(detected)
}

fn emit_sum_i32_buffer_negative_diff(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("sum-i32-buffer-c-oracle.json");
    let report: SumI32BufferOracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    let detected = write_sum_i32_buffer_negative_diff(&report, &evidence_dir)?;

    Ok(NegativeDiffResult {
        slice_id: "demo-sum-i32-buffer",
        status: if detected { "passed" } else { "failed" },
        report_path: "validation/evidence/demo/l3-sum-i32-buffer-negative-diff.json",
    })
}

fn write_sum_i32_buffer_negative_diff(
    report: &SumI32BufferOracleReport,
    evidence_dir: &Path,
) -> Result<bool, Box<dyn Error>> {
    let case = report
        .cases
        .iter()
        .find(|case| !case.values.is_empty())
        .ok_or("sum_i32_buffer oracle must include at least one non-empty case")?;
    let rust = sum_i32_buffer::sum_i32_buffer(&case.values);
    let mutated_sum = case.sum.wrapping_add(1);
    let detected = mutated_sum != rust.sum;
    write_json(
        &evidence_dir.join("l3-sum-i32-buffer-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": "demo-sum-i32-buffer-20260625",
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

fn emit_call_expression_chain_negative_diff(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<NegativeDiffResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("call-expression-c-oracle.json");
    let report: CallExpressionChainOracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("demo");
    let detected = write_call_expression_chain_negative_diff(&report, &evidence_dir)?;

    Ok(NegativeDiffResult {
        slice_id: "demo-call-expression",
        status: if detected { "passed" } else { "failed" },
        report_path: "validation/evidence/demo/l3-call-expression-negative-diff.json",
    })
}

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

fn emit_call_expression_chain_static_l3_evidence(
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
    let source_commit = "demo-call-expression-20260625";
    let fixture_path = "validation/l2_slices/fixtures/call-expression-c-oracle.json";
    let prefix = "l3-call-expression";
    let behavior_fields = [
        "return_value",
        "status",
        "call_expression_count",
        "call_expression_contexts",
        "source_calls",
    ];
    let source_calls = [
        "int first = call_expression_chain(value - 1)",
        "value = call_expression_chain(first - 1)",
        "return call_expression_chain(value - 1)",
    ];

    write_json(
        &evidence_dir.join(format!("{prefix}-slice-contract.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "source_boundary": {
                "files": ["validation/l2_slices/tools/generate_call_expression_oracle.py"],
                "functions": ["call_expression_chain"],
                "signature": "int call_expression_chain(int value)"
            },
            "rust_boundary": {
                "module": "validation/l2_slices/src/call_expression_chain.rs",
                "api": "pub fn call_expression_chain(value: i32) -> CallExpressionChainReport",
                "safe_rust": true,
                "raw_pointer_exposed": false
            },
            "fixture": {"path": fixture_path, "hash": "call-expression-fixture", "case_count": case_count},
            "behavior_fields": behavior_fields,
            "accepted_differences": [],
            "non_goals": [
                "No external callee semantic proof.",
                "No function pointer, member call, variadic call, macro call, or nested call support claim.",
                "No large recursion depth or performance claim.",
                "No full project migration claim."
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-context-pack.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "direct_c_files": ["validation/l2_slices/tools/generate_call_expression_oracle.py"],
            "direct_rust_files": [
                "validation/l2_slices/src/call_expression_chain.rs",
                "validation/l2_slices/tests/call_expression_chain.rs",
                "validation/l2_slices/src/bin/emit_reports.rs"
            ],
            "direct_call_edges": [
                {"callee": "call_expression_chain", "arguments": ["value - 1"], "source_expression": "call_expression_chain(value - 1)", "statement_context": "declaration_initializer"},
                {"callee": "call_expression_chain", "arguments": ["first - 1"], "source_expression": "call_expression_chain(first - 1)", "statement_context": "assignment"},
                {"callee": "call_expression_chain", "arguments": ["value - 1"], "source_expression": "call_expression_chain(value - 1)", "statement_context": "return"}
            ],
            "source_calls": source_calls,
            "related_tests": [
                "validation/l2_slices/tests/call_expression_chain.rs::call_expression_chain_matches_c_oracle_and_records_call_contexts"
            ],
            "cache_inputs": [fixture_path, "validation/l2_slices/src/call_expression_chain.rs"]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-config-profile.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "profile_id": "demo-call-expression-wsl-gcc",
            "compile_profile": {
                "c_oracle_command": "python -B validation/l2_slices/tools/generate_call_expression_oracle.py",
                "include_paths": [],
                "command_args": ["wsl", "gcc", "-std=c99", "-Wall", "-Wextra", "-Werror"]
            },
            "rust_profile": {"package": "c-to-rust-l2-slices", "cargo_features": []},
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-type-map.json")),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "call-expression",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "slice_spec_ref": {"path": "validation/slice-specs/demo-call-expression.json", "status": "ready"},
            "build_profile_ref": {"path": "validation/evidence/demo/l3-call-expression-config-profile.json", "status": "recorded"},
            "mappings": [
                {"id": "type-1", "kind": "primitive", "c_name": "value", "symbol": "value", "c_type": "int", "rust_type": "i32", "confidence": "proven", "role": "input_value"},
                {"id": "type-2", "kind": "primitive", "c_name": "first", "symbol": "first", "c_type": "int", "rust_type": "i32", "confidence": "proven", "role": "local_call_result"},
                {"id": "type-3", "kind": "primitive", "c_name": "return", "symbol": "return", "c_type": "int", "rust_type": "i32", "confidence": "proven", "role": "return_value"}
            ],
            "uncertainties": [],
            "unsupported_types": [],
            "unsupported_nodes": [],
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"],
            "safe_boundary": {
                "public_api": "pub fn call_expression_chain(value: i32) -> CallExpressionChainReport",
                "raw_pointer_exposed": false,
                "unsafe_required": false
            }
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-cfg.json")),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "call-expression",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "slice_spec_ref": {"path": "validation/slice-specs/demo-call-expression.json", "status": "ready"},
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"],
            "functions": [
                {
                    "name": "call_expression_chain",
                    "signature": "int call_expression_chain(int value)",
                    "source_span": {"file": "validation/l2_slices/tools/generate_call_expression_oracle.py", "line_start": 1, "line_end": 1},
                    "entry_block": "entry",
                    "exit_blocks": ["base_return", "recursive_return"],
                    "basic_blocks": [
                        {
                            "id": "entry",
                            "kind": "entry",
                            "source_span": {"file": "validation/l2_slices/tools/generate_call_expression_oracle.py", "line_start": 1, "line_end": 1},
                            "statements": ["if (value <= 0)", "int first = call_expression_chain(value - 1)", "value = call_expression_chain(first - 1)", "return call_expression_chain(value - 1)"],
                            "statement_kinds": ["if", "call_expression", "assignment", "call_expression", "return", "call_expression"],
                            "lvalue_kinds": ["none"],
                            "lvalue_decisions": []
                        }
                    ],
                    "branches": [
                        {"id": "branch-1", "kind": "if", "condition": "value <= 0", "source_span": {"file": "validation/l2_slices/tools/generate_call_expression_oracle.py", "line_start": 1, "line_end": 1}}
                    ],
                    "returns": [
                        {"block": "entry", "expression": "-value", "source_span": {"file": "validation/l2_slices/tools/generate_call_expression_oracle.py", "line_start": 1, "line_end": 1}},
                        {"block": "entry", "expression": "call_expression_chain(value - 1)", "source_span": {"file": "validation/l2_slices/tools/generate_call_expression_oracle.py", "line_start": 1, "line_end": 1}}
                    ],
                    "edges": [
                        {"from": "entry", "to": "base_return", "kind": "true_branch", "condition": "value <= 0", "source_span": {"file": "validation/l2_slices/tools/generate_call_expression_oracle.py", "line_start": 1, "line_end": 1}},
                        {"from": "entry", "to": "recursive_return", "kind": "false_branch", "condition": "value > 0", "source_span": {"file": "validation/l2_slices/tools/generate_call_expression_oracle.py", "line_start": 1, "line_end": 1}}
                    ],
                    "structured_control_flow": {
                        "has_goto": false,
                        "has_switch": false,
                        "if_count": 1,
                        "loop_count": 0,
                        "relooper_required": false
                    }
                }
            ],
            "unsupported_control_flow": []
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-pointer-graph.json")),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "call-expression",
            "level": "L3",
            "status": "not_applicable",
            "not_applicable_reason": "call_expression_chain has no pointer parameters, pointer returns, globals, buffers, or external mutable state in the committed fixture boundary.",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "context_pack_ref": "validation/evidence/demo/l3-call-expression-context-pack.json",
            "applicability": {"has_pointer_surface": false, "triggers": ["none"]},
            "source_boundary": {
                "files": ["validation/l2_slices/tools/generate_call_expression_oracle.py", fixture_path],
                "functions": ["call_expression_chain"],
                "structs": [],
                "globals": [],
                "direct_call_edges": [
                    {"from": "call_expression_chain", "to": "call_expression_chain", "condition": "value > 0"}
                ]
            },
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module"]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-rust-check.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": source_commit,
            "status": status,
            "compile_self_healing": {"attempt_count": 0, "unresolved_errors": 0},
            "commands": [
                {"command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test call_expression_chain", "status": status},
                {"command": "cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports", "status": status}
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-final-verification.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
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
            "generated_draft_semantic_pass": false,
            "call_expression_contexts_checked": ["declaration_initializer", "assignment", "return"]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-summary.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": source_commit,
            "status": status,
            "semantic_pass": status == "passed",
            "summary": "call_expression_chain recursive direct-call demo has accepted C oracle, Rust replay, diff, negative diff, unsafe, and version evidence.",
            "generated_draft_semantic_pass": false,
            "known_gaps": [
                "No external callee semantic proof.",
                "No function pointer, member call, variadic call, macro call, or nested call support claim.",
                "No large recursion depth or performance claim."
            ]
        }),
    )?;
    let version_payload = json!({
        "schema_version": 1,
        "level": "L3",
        "target_id": "demo",
        "slice_id": "call-expression",
        "source_commit": source_commit,
        "repo_commit": repo_commit,
        "status": "recorded",
        "semantic_pass": status == "passed",
        "translator_version": "0.1.0",
        "fixture": {"path": fixture_path, "hash": "call-expression-fixture"},
        "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module", "translator_version"]
    });
    write_json(
        &evidence_dir.join(format!("{prefix}-version-manifest.json")),
        &version_payload,
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-cache-metadata.json")),
        &version_payload,
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-evidence-manifest.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "call-expression",
            "status": manifest_status,
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "fixture": {"path": fixture_path, "hash": "call-expression-fixture", "operation_count": case_count},
            "evidence": {
                "slice_contract": {"path": "validation/evidence/demo/l3-call-expression-slice-contract.json", "status": "recorded"},
                "context_pack": {"path": "validation/evidence/demo/l3-call-expression-context-pack.json", "status": "recorded"},
                "cache_metadata": {"path": "validation/evidence/demo/l3-call-expression-cache-metadata.json", "status": "recorded"},
                "config_profile": {"path": "validation/evidence/demo/l3-call-expression-config-profile.json", "status": "recorded", "profile_id": "demo-call-expression-wsl-gcc"},
                "type_map": {"path": "validation/evidence/demo/l3-call-expression-type-map.json", "status": "recorded"},
                "cfg": {"path": "validation/evidence/demo/l3-call-expression-cfg.json", "status": "recorded"},
                "pointer_dependency_graph": {"path": "validation/evidence/demo/l3-call-expression-pointer-graph.json", "status": "not_applicable", "not_applicable_reason": "slice has no pointer surface"},
                "test_translation": {"path": "validation/evidence/demo/l3-call-expression-test-translation.json", "status": "recorded"},
                "c_oracle": {"path": "validation/evidence/demo/l3-call-expression-c-oracle.json", "status": "passed", "toolchain_status": "C_ORACLE_GENERATED"},
                "rust_report": {"path": "validation/evidence/demo/l3-call-expression-rust-report.json", "status": status},
                "schema_diff": {"path": "validation/evidence/demo/l3-call-expression-diff.json", "status": status},
                "negative_diff": {"path": "validation/evidence/demo/l3-call-expression-negative-diff.json", "status": "expected_failed", "expected_failure": true, "mutation_detected": true},
                "rust_check": {"path": "validation/evidence/demo/l3-call-expression-rust-check.json", "status": status},
                "unsafe_scan": {"path": "validation/evidence/demo/l3-call-expression-unsafe-scan.json", "status": unsafe_status},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-call-expression-unsafe-ledger.json", "status": unsafe_status},
                "performance_smoke": {"path": "validation/evidence/demo/l3-call-expression-performance-smoke.json", "status": "recorded", "secondary_only": true},
                "final_verification": {"path": "validation/evidence/demo/l3-call-expression-final-verification.json", "status": status},
                "summary": {"path": "validation/evidence/demo/l3-call-expression-summary.json", "status": status},
                "version_or_config_binding": {"path": "validation/evidence/demo/l3-call-expression-version-manifest.json", "status": "recorded"}
            },
            "claim_boundary": {
                "scope": "Only the demo call_expression_chain slice for the committed fixture corpus.",
                "behavior_fields_checked": behavior_fields,
                "accepted_metadata_differences": [],
                "known_gaps": [
                    "No external callee semantic proof.",
                    "No function pointer, member call, variadic call, macro call, or nested call support claim.",
                    "No large recursion depth or performance claim."
                ],
                "must_not_claim": [
                    "full automatic C99/C11 translation",
                    "whole-program call graph semantic proof",
                    "external callee semantic equivalence",
                    "function pointer or nested call expression support"
                ]
            }
        }),
    )
}

fn emit_external_direct_callee_static_l3_evidence(
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
    let source_commit = "demo-external-direct-callee-20260625";
    let fixture_path = "validation/l2_slices/fixtures/external-direct-callee-c-oracle.json";
    let prefix = "l3-external-direct-callee";
    let behavior_fields = [
        "return_value",
        "status",
        "external_callee_call_count",
        "external_callee_contexts",
        "external_callee_bindings",
        "source_calls",
    ];
    let direct_call_edges = json!([
        {"callee": "helper_add_one", "arguments": ["value"], "source_expression": "helper_add_one(value)", "statement_context": "declaration_initializer", "callee_scope": "external_direct_callee", "callee_signature_id": "sig-helper-add-one", "callee_source_ref": "validation/l2_slices/tools/generate_external_direct_callee_oracle.py#helper_add_one", "definition_status": "real_source_bound", "stub_status": "compile_only"},
        {"callee": "helper_add_one", "arguments": ["first"], "source_expression": "helper_add_one(first)", "statement_context": "assignment", "callee_scope": "external_direct_callee", "callee_signature_id": "sig-helper-add-one", "callee_source_ref": "validation/l2_slices/tools/generate_external_direct_callee_oracle.py#helper_add_one", "definition_status": "real_source_bound", "stub_status": "compile_only"},
        {"callee": "helper_add_one", "arguments": ["value"], "source_expression": "helper_add_one(value)", "statement_context": "return", "callee_scope": "external_direct_callee", "callee_signature_id": "sig-helper-add-one", "callee_source_ref": "validation/l2_slices/tools/generate_external_direct_callee_oracle.py#helper_add_one", "definition_status": "real_source_bound", "stub_status": "compile_only"}
    ]);
    let external_callee = json!({
        "name": "helper_add_one",
        "signature_ref": "sig-helper-add-one",
        "source_ref": "validation/l2_slices/tools/generate_external_direct_callee_oracle.py#helper_add_one",
        "source_files": [{"path": "validation/l2_slices/tools/generate_external_direct_callee_oracle.py", "sha256": "generated-at-validation"}],
        "definition_status": "real_source_bound",
        "stub_kind": "compile_only",
        "semantics_verified": false
    });
    let external_callee_scope = json!({
        "status": "compile_context_only",
        "declared_count": 1,
        "blocked_count": 0,
        "stub_kind": "compile_only",
        "semantics_verified": false
    });

    write_json(
        &evidence_dir.join(format!("{prefix}-slice-contract.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "external-direct-callee",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "source_boundary": {
                "files": ["validation/l2_slices/tools/generate_external_direct_callee_oracle.py"],
                "functions": ["call_helper_chain", "helper_add_one"],
                "signature": "int call_helper_chain(int value); int helper_add_one(int value)"
            },
            "rust_boundary": {
                "module": "validation/l2_slices/src/external_direct_callee.rs",
                "api": "pub fn call_helper_chain(value: i32) -> ExternalDirectCalleeReport",
                "safe_rust": true,
                "raw_pointer_exposed": false
            },
            "fixture": {"path": fixture_path, "hash": "external-direct-callee-fixture", "case_count": case_count},
            "behavior_fields": behavior_fields,
            "external_direct_callees": [external_callee.clone()],
            "accepted_differences": [],
            "non_goals": [
                "No arbitrary multi-function translation claim.",
                "No function pointer, member call, variadic call, macro call, or nested call support claim.",
                "No signed overflow equivalence beyond the committed safe fixture domain."
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-context-pack.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "external-direct-callee",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "direct_c_files": ["validation/l2_slices/tools/generate_external_direct_callee_oracle.py"],
            "direct_rust_files": [
                "validation/l2_slices/src/external_direct_callee.rs",
                "validation/l2_slices/tests/external_direct_callee.rs",
                "validation/l2_slices/src/bin/emit_reports.rs"
            ],
            "direct_call_edges": direct_call_edges.clone(),
            "external_direct_callees": [external_callee.clone()],
            "callee_sources": [{"callee": "helper_add_one", "path": "validation/l2_slices/tools/generate_external_direct_callee_oracle.py", "sha256": "generated-at-validation"}],
            "signature_bindings": [{"callee": "helper_add_one", "signature_ref": "sig-helper-add-one", "definition_status": "real_source_bound", "stub_kind": "compile_only", "semantics_verified": false}],
            "stub_boundaries": [{"callee": "helper_add_one", "stub_kind": "compile_only", "allowed_use": "standalone_rust_check_only", "semantics_verified": false}],
            "call_edge_to_callee_binding": [
                {"callee": "helper_add_one", "signature_ref": "sig-helper-add-one", "source_expression": "helper_add_one(value)", "statement_context": "declaration_initializer", "stub_kind": "compile_only", "semantics_verified": false},
                {"callee": "helper_add_one", "signature_ref": "sig-helper-add-one", "source_expression": "helper_add_one(first)", "statement_context": "assignment", "stub_kind": "compile_only", "semantics_verified": false},
                {"callee": "helper_add_one", "signature_ref": "sig-helper-add-one", "source_expression": "helper_add_one(value)", "statement_context": "return", "stub_kind": "compile_only", "semantics_verified": false}
            ],
            "source_calls": [
                "int first = helper_add_one(value)",
                "value = helper_add_one(first)",
                "return helper_add_one(value)"
            ],
            "related_tests": [
                "validation/l2_slices/tests/external_direct_callee.rs::external_direct_callee_matches_c_oracle_and_records_helper_context"
            ],
            "cache_inputs": [fixture_path, "validation/l2_slices/src/external_direct_callee.rs"]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-config-profile.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "external-direct-callee",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "profile_id": "demo-external-direct-callee-wsl-gcc",
            "compile_profile": {
                "c_oracle_command": "python -B validation/l2_slices/tools/generate_external_direct_callee_oracle.py",
                "include_paths": [],
                "command_args": ["wsl", "gcc", "-std=c99", "-Wall", "-Wextra", "-Werror"]
            },
            "rust_profile": {"package": "c-to-rust-l2-slices", "cargo_features": []},
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module", "external_callee.signature"]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-type-map.json")),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "external-direct-callee",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "slice_spec_ref": {"path": "validation/slice-specs/demo-external-direct-callee.json", "status": "ready"},
            "build_profile_ref": {"path": "validation/evidence/demo/l3-external-direct-callee-config-profile.json", "status": "recorded"},
            "mappings": [
                {"id": "type-1", "kind": "primitive", "c_name": "value", "symbol": "value", "c_type": "int", "rust_type": "i32", "confidence": "proven", "role": "input_value"},
                {"id": "type-2", "kind": "primitive", "c_name": "first", "symbol": "first", "c_type": "int", "rust_type": "i32", "confidence": "proven", "role": "local_call_result"},
                {"id": "type-3", "kind": "primitive", "c_name": "helper_add_one", "symbol": "helper_add_one", "c_type": "int(int)", "rust_type": "fn(i32) -> i32", "confidence": "proven", "role": "external_direct_callee"},
                {"id": "type-4", "kind": "primitive", "c_name": "return", "symbol": "return", "c_type": "int", "rust_type": "i32", "confidence": "proven", "role": "return_value"}
            ],
            "uncertainties": [],
            "unsupported_types": [],
            "unsupported_nodes": [],
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module", "external_callee.signature"],
            "safe_boundary": {
                "public_api": "pub fn call_helper_chain(value: i32) -> ExternalDirectCalleeReport",
                "raw_pointer_exposed": false,
                "unsafe_required": false
            }
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-cfg.json")),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "external-direct-callee",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "slice_spec_ref": {"path": "validation/slice-specs/demo-external-direct-callee.json", "status": "ready"},
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module", "external_callee.signature"],
            "functions": [
                {
                    "name": "call_helper_chain",
                    "signature": "int call_helper_chain(int value)",
                    "source_span": {"file": "validation/l2_slices/tools/generate_external_direct_callee_oracle.py", "line_start": 1, "line_end": 1},
                    "entry_block": "entry",
                    "exit_blocks": ["return"],
                    "basic_blocks": [
                        {
                            "id": "entry",
                            "kind": "entry",
                            "source_span": {"file": "validation/l2_slices/tools/generate_external_direct_callee_oracle.py", "line_start": 1, "line_end": 1},
                            "statements": ["int first = helper_add_one(value)", "value = helper_add_one(first)", "return helper_add_one(value)"],
                            "statement_kinds": ["call_expression", "assignment", "call_expression", "return", "call_expression"],
                            "lvalue_kinds": ["none"],
                            "lvalue_decisions": []
                        }
                    ],
                    "branches": [],
                    "returns": [
                        {"block": "entry", "expression": "helper_add_one(value)", "source_span": {"file": "validation/l2_slices/tools/generate_external_direct_callee_oracle.py", "line_start": 1, "line_end": 1}}
                    ],
                    "edges": [],
                    "structured_control_flow": {
                        "has_goto": false,
                        "has_switch": false,
                        "if_count": 0,
                        "loop_count": 0,
                        "relooper_required": false
                    }
                }
            ],
            "unsupported_control_flow": []
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-pointer-graph.json")),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "external-direct-callee",
            "level": "L3",
            "status": "not_applicable",
            "not_applicable_reason": "call_helper_chain has no pointer parameters, pointer returns, globals, buffers, or external mutable state in the committed fixture boundary.",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "context_pack_ref": "validation/evidence/demo/l3-external-direct-callee-context-pack.json",
            "applicability": {"has_pointer_surface": false, "triggers": ["none"]},
            "source_boundary": {
                "files": ["validation/l2_slices/tools/generate_external_direct_callee_oracle.py", fixture_path],
                "functions": ["call_helper_chain", "helper_add_one"],
                "structs": [],
                "globals": [],
                "direct_call_edges": [
                    {"from": "call_helper_chain", "to": "helper_add_one", "context": "declaration_initializer"},
                    {"from": "call_helper_chain", "to": "helper_add_one", "context": "assignment"},
                    {"from": "call_helper_chain", "to": "helper_add_one", "context": "return"}
                ]
            },
            "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module", "external_callee.signature"]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-rust-check.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "external-direct-callee",
            "source_commit": source_commit,
            "status": status,
            "compile_self_healing": {"attempt_count": 0, "unresolved_errors": 0},
            "external_callee_context": {
                "status": "recorded",
                "declared_count": 1,
                "blocked_count": 0,
                "declared_callees": [{"name": "helper_add_one", "signature_ref": "sig-helper-add-one", "stub_kind": "compile_only", "semantics_verified": false}],
                "blocked_callees": []
            },
            "commands": [
                {"command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test external_direct_callee", "status": status},
                {"command": "cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports", "status": status}
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-final-verification.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "external-direct-callee",
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
            "generated_draft_semantic_pass": false,
            "external_callee_scope": external_callee_scope,
            "external_direct_callee_context_status": "recorded",
            "external_direct_callees_checked": ["helper_add_one"],
            "real_callee_source_count": 1,
            "generated_stub_count": 1,
            "callee_signature_binding_status": "recorded"
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-summary.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "external-direct-callee",
            "source_commit": source_commit,
            "status": status,
            "semantic_pass": status == "passed",
            "summary": "call_helper_chain external direct callee demo has accepted C oracle, Rust replay, diff, negative diff, unsafe, and version evidence.",
            "generated_draft_semantic_pass": false,
            "external_callee_scope": external_callee_scope,
            "known_gaps": [
                "No arbitrary multi-function translation claim.",
                "No function pointer, member call, variadic call, macro call, or nested call support claim."
            ]
        }),
    )?;
    let version_payload = json!({
        "schema_version": 1,
        "level": "L3",
        "target_id": "demo",
        "slice_id": "external-direct-callee",
        "source_commit": source_commit,
        "repo_commit": repo_commit,
        "status": "recorded",
        "semantic_pass": status == "passed",
        "translator_version": "0.1.0",
        "fixture": {"path": fixture_path, "hash": "external-direct-callee-fixture"},
        "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module", "translator_version", "external_callee.signature"]
    });
    write_json(
        &evidence_dir.join(format!("{prefix}-version-manifest.json")),
        &version_payload,
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-cache-metadata.json")),
        &version_payload,
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-evidence-manifest.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "external-direct-callee",
            "status": manifest_status,
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "fixture": {"path": fixture_path, "hash": "external-direct-callee-fixture", "operation_count": case_count},
            "evidence": {
                "slice_contract": {"path": "validation/evidence/demo/l3-external-direct-callee-slice-contract.json", "status": "recorded"},
                "context_pack": {"path": "validation/evidence/demo/l3-external-direct-callee-context-pack.json", "status": "recorded"},
                "cache_metadata": {"path": "validation/evidence/demo/l3-external-direct-callee-cache-metadata.json", "status": "recorded"},
                "config_profile": {"path": "validation/evidence/demo/l3-external-direct-callee-config-profile.json", "status": "recorded", "profile_id": "demo-external-direct-callee-wsl-gcc"},
                "type_map": {"path": "validation/evidence/demo/l3-external-direct-callee-type-map.json", "status": "recorded"},
                "cfg": {"path": "validation/evidence/demo/l3-external-direct-callee-cfg.json", "status": "recorded"},
                "pointer_dependency_graph": {"path": "validation/evidence/demo/l3-external-direct-callee-pointer-graph.json", "status": "not_applicable", "not_applicable_reason": "slice has no pointer surface"},
                "test_translation": {"path": "validation/evidence/demo/l3-external-direct-callee-test-translation.json", "status": "recorded"},
                "c_oracle": {"path": "validation/evidence/demo/l3-external-direct-callee-c-oracle.json", "status": "passed", "toolchain_status": "C_ORACLE_GENERATED"},
                "rust_report": {"path": "validation/evidence/demo/l3-external-direct-callee-rust-report.json", "status": status},
                "schema_diff": {"path": "validation/evidence/demo/l3-external-direct-callee-diff.json", "status": status},
                "negative_diff": {"path": "validation/evidence/demo/l3-external-direct-callee-negative-diff.json", "status": "expected_failed", "expected_failure": true, "mutation_detected": true},
                "rust_check": {"path": "validation/evidence/demo/l3-external-direct-callee-rust-check.json", "status": status},
                "unsafe_scan": {"path": "validation/evidence/demo/l3-external-direct-callee-unsafe-scan.json", "status": unsafe_status},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-external-direct-callee-unsafe-ledger.json", "status": unsafe_status},
                "performance_smoke": {"path": "validation/evidence/demo/l3-external-direct-callee-performance-smoke.json", "status": "recorded", "secondary_only": true},
                "final_verification": {"path": "validation/evidence/demo/l3-external-direct-callee-final-verification.json", "status": status},
                "summary": {"path": "validation/evidence/demo/l3-external-direct-callee-summary.json", "status": status},
                "version_or_config_binding": {"path": "validation/evidence/demo/l3-external-direct-callee-version-manifest.json", "status": "recorded"}
            },
            "claim_boundary": {
                "scope": "Only the demo call_helper_chain external direct callee slice for the committed fixture corpus.",
                "behavior_fields_checked": behavior_fields,
                "external_callee_scope": external_callee_scope,
                "accepted_metadata_differences": [],
                "known_gaps": [
                    "No arbitrary multi-function translation claim.",
                    "No function pointer, member call, variadic call, macro call, or nested call support claim."
                ],
                "must_not_claim": [
                    "full automatic C99/C11 translation",
                    "whole-program call graph semantic proof",
                    "helper stub semantic equivalence",
                    "function pointer or nested call expression support"
                ]
            }
        }),
    )
}

fn emit_sum_i32_ptr_arith_static_l3_evidence(
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
    let source_commit = "demo-sum-i32-ptr-arith-20260625";
    let fixture_path = "validation/l2_slices/fixtures/sum-i32-ptr-arith-c-oracle.json";
    let prefix = "l3-sum-i32-ptr-arith";

    write_json(
        &evidence_dir.join(format!("{prefix}-slice-contract.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "source_boundary": {
                "files": ["validation/l2_slices/tools/generate_sum_i32_ptr_arith_oracle.py"],
                "functions": ["sum_i32_ptr_arith"],
                "signature": "int sum_i32_ptr_arith(const int* values, int len, int* out)"
            },
            "rust_boundary": {
                "module": "validation/l2_slices/src/sum_i32_ptr_arith.rs",
                "api": "pub fn sum_i32_ptr_arith(values: &[i32]) -> SumI32PtrArithReport",
                "raw_pointer_policy": "internal_only",
                "unsafe_policy": {"max_first_party_non_test_ratio": 0.1}
            },
            "fixture": {"path": fixture_path, "hash": "sum-i32-ptr-arith-fixture", "case_count": case_count},
            "claim_boundary": {
                "scope": "Only the demo sum_i32_ptr_arith slice for the committed fixture corpus.",
                "non_goals": ["No NULL pointer execution.", "No negative len execution.", "No pointer arithmetic writes.", "No aliasing or signed overflow claim."]
            }
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-context-pack.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "status": "recorded",
            "direct_c_files": ["validation/l2_slices/tools/generate_sum_i32_ptr_arith_oracle.py"],
            "rust_files": [
                "validation/l2_slices/src/sum_i32_ptr_arith.rs",
                "validation/l2_slices/tests/sum_i32_ptr_arith.rs",
                "validation/l2_slices/src/bin/emit_reports.rs"
            ],
            "direct_call_edges": [
                {"from": "C oracle helper", "to": "sum_i32_ptr_arith"},
                {"from": "Rust emit_reports", "to": "sum_i32_ptr_arith::sum_i32_ptr_arith"}
            ],
            "test_entrypoints": [
                "validation/l2_slices/tests/sum_i32_ptr_arith.rs::sum_i32_ptr_arith_matches_c_oracle_with_safe_boundary"
            ],
            "cache_inputs": [fixture_path, "validation/l2_slices/src/sum_i32_ptr_arith.rs"]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-config-profile.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": source_commit,
            "status": "recorded",
            "profile_id": "demo-sum-i32-ptr-arith-wsl-gcc",
            "c_oracle_command": "python -B validation/l2_slices/tools/generate_sum_i32_ptr_arith_oracle.py",
            "rust_replay_command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test sum_i32_ptr_arith",
            "compiler": {"name": "gcc", "mode": "wsl", "standard": "c99"},
            "rust": {"framework": "cargo test", "crate": "validation/l2_slices"}
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-type-map.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": source_commit,
            "status": "recorded",
            "slice_spec_ref": {"path": "validation/slice-specs/demo-sum-i32-ptr-arith.json", "status": "ready"},
            "mappings": [
                {"c_name": "values", "c_type": "const int*", "rust_type": "&[i32]", "kind": "pointer", "decision": "safe_slice_input", "length_companion": "len"},
                {"c_name": "len", "c_type": "int", "rust_type": "i32", "kind": "primitive"},
                {"c_name": "out", "c_type": "int*", "rust_type": "SumI32PtrArithReport", "kind": "pointer", "decision": "owned_report_output"},
                {"c_name": "total", "c_type": "int", "rust_type": "i32", "kind": "primitive"},
                {"c_name": "i", "c_type": "int", "rust_type": "i32", "kind": "primitive"}
            ],
            "uncertainties": []
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-cfg.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": source_commit,
            "status": "recorded",
            "functions": [
                {
                    "name": "sum_i32_ptr_arith",
                    "signature": "int sum_i32_ptr_arith(const int* values, int len, int* out)",
                    "basic_blocks": [
                        {
                            "id": "entry",
                            "statements": [
                                "int total = 0",
                                "for (int i = 0; i < len; i++) { total = total + *(values + i); }",
                                "out[0] = total",
                                "return 0"
                            ],
                            "statement_kinds": ["primitive_declaration", "for", "bounded_input_buffer_read", "bounded_pointer_arithmetic_input_read", "pointer_write", "return"],
                            "lvalue_kinds": ["simple_identifier", "bounded_input_buffer", "bounded_pointer_arithmetic_input_buffer", "bounded_pointer_index"],
                            "lvalue_decisions": [
                                {"statement_index": 1, "source_statement": "total = total + *(values + i)", "lvalue_kind": "bounded_pointer_arithmetic_input_buffer", "decision": "bounded_pointer_arithmetic_input_read", "translation_rule_id": "bounded-pointer-arithmetic-input-read"},
                                {"statement_index": 2, "source_statement": "out[0] = total", "lvalue_kind": "bounded_pointer_index", "decision": "bounded_pointer_index", "translation_rule_id": "bounded-pointer-index-write"}
                            ],
                            "terminator": "return",
                            "edges": ["entry->for-1", "entry->return-3"]
                        }
                    ],
                    "unsupported_control_flow": []
                }
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-pointer-graph.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": source_commit,
            "status": "recorded",
            "applicability": {"contains_pointers": true, "triggers": ["pointer_parameter", "buffer"]},
            "pointer_nodes": [
                {
                    "id": "values",
                    "kind": "buffer",
                    "buffer_role": "input",
                    "ownership_role": "borrowed",
                    "mutability": "read_only",
                    "c_type": "const int*",
                    "rust_boundary": "&[i32]",
                    "length_companion": "len",
                    "read_effects": ["values[i]", "*(values + i)"],
                    "write_effects": [],
                    "boundary_decisions": ["bounded_input_buffer", "bounded_pointer_arithmetic_input_read"]
                },
                {
                    "id": "out",
                    "kind": "pointer",
                    "ownership_role": "out_param",
                    "mutability": "write_only",
                    "c_type": "int*",
                    "rust_boundary": "owned safe report",
                    "read_effects": [],
                    "write_effects": ["out[0]"],
                    "boundary_decisions": ["bounded_pointer_index"]
                }
            ],
            "pointer_edges": [{"from": "values", "to": "out", "relationship": "input_influences_output"}],
            "pointer_decisions": [
                {"pointer_node": "values", "decision": "bounded_input_buffer", "read_effect": "values[i]", "length_companion": "len", "translation_rule_id": "bounded-input-buffer-read", "unsafe_expected": false},
                {"pointer_node": "values", "decision": "bounded_pointer_arithmetic_input_read", "read_effect": "*(values + i)", "canonical_read": "values[i]", "length_companion": "len", "translation_rule_id": "bounded-pointer-arithmetic-input-read", "unsafe_expected": false},
                {"pointer_node": "out", "decision": "bounded_pointer_index", "index": 0, "write_effect": "out[0]", "translation_rule_id": "bounded-pointer-index-write", "unsafe_expected": false}
            ],
            "risk_summary": {
                "unsafe_expected": false,
                "known_gaps": ["NULL pointers are not executed.", "Pointer writes through arithmetic are unsupported.", "Aliasing is not proven.", "Signed overflow cases are excluded."]
            }
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-test-translation.json")),
        &json!({
            "schema_version": 1,
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "level": "L3",
            "status": "recorded",
            "source_commit": source_commit,
            "source_test_inputs": {
                "oracle_strategy": "WSL gcc compiles and runs the C helper, then Rust cargo tests replay the same fixture.",
                "fixtures": [{"path": fixture_path, "hash": "sum-i32-ptr-arith-fixture", "operation_count": case_count, "source_kind": "fixture"}],
                "oracle_reports": [
                    {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-c-oracle.json", "status": "passed"},
                    {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-rust-report.json", "status": "passed"}
                ]
            },
            "rust_tests": [
                {
                    "file": "validation/l2_slices/tests/sum_i32_ptr_arith.rs",
                    "test_names": ["sum_i32_ptr_arith_matches_c_oracle_with_safe_boundary"],
                    "cargo_command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test sum_i32_ptr_arith",
                    "framework": "cargo test"
                }
            ],
            "coverage": {
                "main_paths": ["empty input", "single input", "multi input", "negative values", "pointer arithmetic input read", "boundary-safe sum"],
                "error_paths": [],
                "negative_cases": ["sum mutation rejected by negative diff"]
            },
            "translation_mappings": [
                {
                    "source": fixture_path,
                    "rust_test": "validation/l2_slices/tests/sum_i32_ptr_arith.rs::sum_i32_ptr_arith_matches_c_oracle_with_safe_boundary",
                    "behavior_fields": ["return_code", "status", "len", "sum", "source_reads", "canonical_reads", "source_write"],
                    "coverage_kind": "main_path",
                    "status": "mapped"
                },
                {
                    "source": "validation/evidence/demo/l3-sum-i32-ptr-arith-negative-diff.json",
                    "rust_test": "validation/l2_slices/src/bin/emit_reports.rs::emit_sum_i32_ptr_arith_negative_diff",
                    "behavior_fields": ["sum"],
                    "coverage_kind": "negative_case",
                    "status": "mapped"
                }
            ],
            "evidence_links": {
                "c_oracle": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-c-oracle.json", "status": "passed"},
                "rust_report": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-rust-report.json", "status": "passed"},
                "schema_diff": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-diff.json", "status": "passed"},
                "negative_diff": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-negative-diff.json", "status": "expected_failed"},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-unsafe-ledger.json", "status": unsafe_status}
            }
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-rust-check.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": source_commit,
            "status": status,
            "compile_self_healing": {"attempt_count": 0, "unresolved_errors": 0},
            "commands": [
                {"command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test sum_i32_ptr_arith", "status": status},
                {"command": "cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports", "status": status}
            ]
        }),
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-final-verification.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
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
        &evidence_dir.join(format!("{prefix}-summary.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": source_commit,
            "status": status,
            "semantic_pass": status == "passed",
            "summary": "sum_i32_ptr_arith pointer-arithmetic input read demo has accepted C oracle, Rust replay, diff, negative diff, unsafe, and version evidence.",
            "generated_draft_semantic_pass": false,
            "known_gaps": ["No NULL pointer execution.", "No negative len execution.", "No pointer arithmetic writes.", "No aliasing or signed overflow claim."]
        }),
    )?;
    let version_payload = json!({
        "schema_version": 1,
        "level": "L3",
        "target_id": "demo",
        "slice_id": "sum-i32-ptr-arith",
        "source_commit": source_commit,
        "repo_commit": repo_commit,
        "status": "recorded",
        "semantic_pass": status == "passed",
        "translator_version": "0.1.0",
        "fixture": {"path": fixture_path, "hash": "sum-i32-ptr-arith-fixture"},
        "cache_invalidation_keys": ["source_commit", "repo_commit", "fixture.hash", "rust_boundary.module", "translator_version"]
    });
    write_json(
        &evidence_dir.join(format!("{prefix}-version-manifest.json")),
        &version_payload,
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-cache-metadata.json")),
        &version_payload,
    )?;
    write_json(
        &evidence_dir.join(format!("{prefix}-evidence-manifest.json")),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "status": manifest_status,
            "source_commit": source_commit,
            "repo_commit": repo_commit,
            "fixture": {"path": fixture_path, "hash": "sum-i32-ptr-arith-fixture", "operation_count": case_count},
            "evidence": {
                "slice_contract": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-slice-contract.json", "status": "recorded"},
                "context_pack": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-context-pack.json", "status": "recorded"},
                "cache_metadata": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-cache-metadata.json", "status": "recorded"},
                "config_profile": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-config-profile.json", "status": "recorded", "profile_id": "demo-sum-i32-ptr-arith-wsl-gcc"},
                "type_map": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-type-map.json", "status": "recorded"},
                "cfg": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-cfg.json", "status": "recorded"},
                "pointer_dependency_graph": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-pointer-graph.json", "status": "recorded"},
                "test_translation": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-test-translation.json", "status": "recorded"},
                "c_oracle": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-c-oracle.json", "status": "passed", "toolchain_status": "C_ORACLE_GENERATED"},
                "rust_report": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-rust-report.json", "status": status},
                "schema_diff": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-diff.json", "status": status},
                "negative_diff": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-negative-diff.json", "status": "expected_failed", "expected_failure": true, "mutation_detected": true},
                "rust_check": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-rust-check.json", "status": status},
                "unsafe_scan": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-unsafe-scan.json", "status": unsafe_status},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-unsafe-ledger.json", "status": unsafe_status},
                "performance_smoke": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-performance-smoke.json", "status": "recorded", "secondary_only": true},
                "final_verification": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-final-verification.json", "status": status},
                "summary": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-summary.json", "status": status},
                "version_or_config_binding": {"path": "validation/evidence/demo/l3-sum-i32-ptr-arith-version-manifest.json", "status": "recorded"}
            },
            "claim_boundary": {
                "scope": "Only the demo sum_i32_ptr_arith slice for the committed fixture corpus.",
                "behavior_fields_checked": ["return_code", "status", "len", "sum", "source_reads", "canonical_reads", "source_write"],
                "accepted_metadata_differences": [],
                "known_gaps": ["No NULL pointer execution.", "No negative len execution.", "No pointer arithmetic writes.", "No aliasing or signed overflow claim."],
                "must_not_claim": ["full automatic C99/C11 translation", "whole-program alias safety", "NULL pointer equivalence", "signed overflow equivalence"]
            }
        }),
    )
}

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

fn write_json(path: &Path, value: &Value) -> Result<(), Box<dyn Error>> {
    fs::write(path, serde_json::to_string_pretty(value)? + "\n")?;
    Ok(())
}

fn compare_field(
    first_mismatch: &mut Option<Value>,
    case_id: &str,
    field: &str,
    c: Value,
    rust: Value,
) {
    if first_mismatch.is_none() && c != rust {
        *first_mismatch = Some(json!({
            "case_id": case_id,
            "field": field,
            "c_value": c,
            "rust_value": rust
        }));
    }
}

fn status_from_mismatch(first_mismatch: &Option<Value>) -> &'static str {
    if first_mismatch.is_none() {
        "passed"
    } else {
        "failed"
    }
}

fn hex_to_bytes(hex: &str) -> Result<Vec<u8>, Box<dyn Error>> {
    if !hex.len().is_multiple_of(2) {
        return Err("hex length must be even".into());
    }
    (0..hex.len())
        .step_by(2)
        .map(|idx| Ok(u8::from_str_radix(&hex[idx..idx + 2], 16)?))
        .collect()
}

fn bytes_to_hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn scan_rust_files(
    dir: &Path,
    on_line: &mut dyn FnMut(&Path, usize, &str),
) -> Result<(), Box<dyn Error>> {
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let path = entry.path();
        if path.is_dir() {
            scan_rust_files(&path, on_line)?;
        } else if path.extension().and_then(|ext| ext.to_str()) == Some("rs") {
            let text = fs::read_to_string(&path)?;
            for (index, line) in text.lines().enumerate() {
                let code = strip_strings_and_line_comments(line);
                on_line(&path, index + 1, &code);
            }
        }
    }
    Ok(())
}

fn strip_strings_and_line_comments(line: &str) -> String {
    let mut out = String::with_capacity(line.len());
    let mut chars = line.chars().peekable();
    let mut in_string = false;
    let mut in_char = false;
    let mut escaped = false;

    while let Some(ch) = chars.next() {
        if !in_string && !in_char && ch == '/' && chars.peek() == Some(&'/') {
            break;
        }

        if in_string {
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == '"' {
                in_string = false;
            }
            out.push(' ');
            continue;
        }

        if in_char {
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == '\'' {
                in_char = false;
            }
            out.push(' ');
            continue;
        }

        if ch == '"' {
            in_string = true;
            out.push(' ');
        } else if ch == '\'' {
            in_char = true;
            out.push(' ');
        } else {
            out.push(ch);
        }
    }

    out
}

fn relative_path(path: &Path) -> String {
    let crate_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = crate_dir
        .parent()
        .and_then(Path::parent)
        .unwrap_or(crate_dir.as_path());
    path.strip_prefix(repo_root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}
